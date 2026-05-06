import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

from db import (
    get_bug_mapping_count,
    get_connection,
    get_run_count,
    get_scenario_result_count,
    init_schema,
    upsert_scenario_history,
)


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
MANIFESTS_DIR = Path(os.getenv("MANIFESTS_DIR", PROJECT_ROOT / "manifests"))
BUG_TRACKER_FILE = Path(os.getenv("BUG_TRACKER_FILE", PROJECT_ROOT / "bug-tracker.json"))
RUN_ALIASES_FILE = Path(os.getenv("RUN_ALIASES_FILE", PROJECT_ROOT / "run-aliases.json"))

DOORS_TAG_RE = re.compile(r"@?(DOORS-\d+|ABS-\d+)", re.IGNORECASE)
EXPLICIT_ID_TAG_RE = re.compile(r"@?id:(.+)", re.IGNORECASE)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def parse_timestamp(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    normalized = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def parse_duration_seconds(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    raw = str(value).strip()
    if not raw:
        return None

    if raw.lower().endswith("s") and not raw.upper().startswith("PT"):
        try:
            return float(raw[:-1])
        except ValueError:
            return None

    match = re.fullmatch(
        r"P(?:(?P<days>\d+(?:\.\d+)?)D)?"
        r"(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?"
        r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
        r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?",
        raw.upper(),
    )
    if match:
        parts = {key: float(val) if val else 0.0 for key, val in match.groupdict().items()}
        return (
            parts["days"] * 86400
            + parts["hours"] * 3600
            + parts["minutes"] * 60
            + parts["seconds"]
        )

    try:
        return float(raw)
    except ValueError:
        return None


def load_aliases():
    if not RUN_ALIASES_FILE.exists():
        return {}
    return load_json(RUN_ALIASES_FILE)


def source_name(path):
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def migration_id(source_file, source_hash):
    return hashlib.sha256(f"{source_file}:{source_hash}".encode("utf-8")).hexdigest()


def existing_successful_import(conn, source_file, source_hash):
    return conn.execute(
        """
        SELECT 1
        FROM migration_imports
        WHERE source_file = ? AND source_hash = ? AND status = 'IMPORTED'
        LIMIT 1
        """,
        [source_file, source_hash],
    ).fetchone() is not None


def record_import(conn, source_file, source_hash, status, rows_imported, error_message=None):
    conn.execute(
        """
        INSERT INTO migration_imports (
          id, source_file, source_hash, status, started_at, finished_at, rows_imported, error_message
        ) VALUES (?, ?, ?, ?, current_timestamp, current_timestamp, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          status = excluded.status,
          finished_at = excluded.finished_at,
          rows_imported = excluded.rows_imported,
          error_message = excluded.error_message
        """,
        [
            migration_id(source_file, source_hash),
            source_file,
            source_hash,
            status,
            rows_imported,
            error_message,
        ],
    )


def extract_doors_number(scenario):
    direct = scenario.get("doorsAbsNumber") or scenario.get("doors_number")
    if direct:
        return str(direct)
    for tag in scenario.get("tags", []) or []:
        match = DOORS_TAG_RE.fullmatch(str(tag).strip())
        if match:
            return match.group(1).upper()
    return None


def extract_explicit_id(scenario):
    for tag in scenario.get("tags", []) or []:
        match = EXPLICIT_ID_TAG_RE.fullmatch(str(tag).strip())
        if match:
            return match.group(1).strip()
    return None


def first_non_empty(mapping, keys):
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def parse_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def scenario_identity(scenario, index):
    feature_file = first_non_empty(
        scenario,
        ["featureFile", "feature_file", "featureUri", "uri", "feature"],
    )
    feature_line = parse_int(first_non_empty(scenario, ["featureLine", "feature_line", "line"]))
    explicit_id = extract_explicit_id(scenario)
    doors_number = extract_doors_number(scenario)
    scenario_id = first_non_empty(scenario, ["id", "scenarioId"])
    name = str(first_non_empty(scenario, ["name"]) or f"scenario-{index}")

    if feature_file and feature_line:
        key = f"{feature_file}:{feature_line}"
        return key, "feature_line", key, str(feature_file), feature_line, doors_number
    if explicit_id:
        return f"id:{explicit_id}", "explicit_tag", explicit_id, str(feature_file) if feature_file else None, feature_line, doors_number
    if doors_number:
        return f"doors:{doors_number}", "doors_number", doors_number, str(feature_file) if feature_file else None, feature_line, doors_number
    if feature_file:
        key = f"{feature_file}:{name}"
        return f"feature_name:{key}", "feature_name", key, str(feature_file), feature_line, doors_number
    if scenario_id:
        return f"scenario_id:{scenario_id}", "scenario_id", str(scenario_id), None, feature_line, doors_number
    return f"name:{name}", "scenario_name", name, None, feature_line, doors_number


def normalize_status(value):
    status = str(value or "UNKNOWN").upper()
    if status not in {"PASSED", "FAILED", "SKIPPED", "BROKEN", "UNKNOWN"}:
        return "UNKNOWN"
    return status


def first_error_message(scenario):
    direct = scenario.get("errorMessage")
    if direct:
        return str(direct)

    for attempt in scenario.get("attempts", []) or []:
        message = attempt.get("errorMessage")
        if message:
            return str(message)

    for step in scenario.get("steps", []) or []:
        message = step.get("errorMessage")
        if message:
            return str(message)
    return None


def attachment_paths(scenario):
    screenshot_path = None
    video_path = None
    for attachment in scenario.get("attachments", []) or []:
        path = attachment.get("path")
        if not path:
            continue
        media_type = str(attachment.get("type") or "").lower()
        name = str(attachment.get("name") or "").lower()
        if screenshot_path is None and (media_type == "image/png" or "screenshot" in name):
            screenshot_path = str(path)
        if video_path is None and (media_type == "video/mp4" or "video" in name):
            video_path = str(path)
    return screenshot_path, video_path


def import_bug_tracker(conn):
    if not BUG_TRACKER_FILE.exists():
        return 0

    source_file = source_name(BUG_TRACKER_FILE)
    source_hash = sha256_file(BUG_TRACKER_FILE)
    data = load_json(BUG_TRACKER_FILE)
    mappings = data.get("mappings", {})

    for doors_number, bug in mappings.items():
        conn.execute(
            """
            INSERT INTO bug_mappings (doors_number, jira_key, jira_status, source, first_seen_at, updated_at)
            VALUES (?, ?, ?, 'bug-tracker.json', ?, ?)
            ON CONFLICT(doors_number) DO UPDATE SET
              jira_key = excluded.jira_key,
              jira_status = excluded.jira_status,
              updated_at = excluded.updated_at
            """,
            [
                doors_number,
                bug.get("jiraKey"),
                bug.get("status"),
                parse_timestamp(bug.get("firstSeen")),
                parse_timestamp(bug.get("lastSeen")),
            ],
        )

    record_import(conn, source_file, source_hash, "IMPORTED", len(mappings))
    return len(mappings)


def bug_mapping_lookup():
    if not BUG_TRACKER_FILE.exists():
        return {}
    return load_json(BUG_TRACKER_FILE).get("mappings", {})


def insert_scenario_definition(conn, manifest, scenario, index, run_started_at):
    scenario_uid, identity_source, identity_key, feature_file, feature_line, doors_number = scenario_identity(scenario, index)
    run_id = manifest["runId"]

    conn.execute(
        """
        INSERT INTO scenario_definitions (
          scenario_uid, identity_source, identity_key, current_name, current_feature_file,
          current_feature_line, doors_number, first_seen_run_id, last_seen_run_id,
          first_seen_at, last_seen_at, active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, true)
        ON CONFLICT(scenario_uid) DO UPDATE SET
          current_name = excluded.current_name,
          current_feature_file = excluded.current_feature_file,
          current_feature_line = excluded.current_feature_line,
          doors_number = COALESCE(excluded.doors_number, scenario_definitions.doors_number),
          last_seen_run_id = excluded.last_seen_run_id,
          last_seen_at = excluded.last_seen_at,
          active = true
        """,
        [
            scenario_uid,
            identity_source,
            identity_key,
            scenario.get("name") or f"scenario-{index}",
            feature_file,
            feature_line,
            doors_number,
            run_id,
            run_id,
            run_started_at,
            run_started_at,
        ],
    )
    return scenario_uid, feature_file, feature_line, doors_number


def import_manifest(conn, path, aliases, bug_lookup):
    source_file = source_name(path)
    source_hash = sha256_file(path)
    if existing_successful_import(conn, source_file, source_hash):
        return "skipped", 0

    manifest = load_json(path)
    run_id = manifest["runId"]
    existing_run = conn.execute(
        "SELECT source_manifest_hash FROM runs WHERE id = ?",
        [run_id],
    ).fetchone()
    if existing_run:
        if existing_run[0] != source_hash:
            message = f"run_id '{run_id}' already exists with a different manifest checksum"
            record_import(conn, source_file, source_hash, "FAILED", 0, message)
            raise RuntimeError(message)
        record_import(conn, source_file, source_hash, "IMPORTED", 0)
        return "skipped", 0

    started_at = parse_timestamp(manifest.get("timestamp"))
    duration_seconds = parse_duration_seconds(manifest.get("duration"))
    finished_at = started_at + timedelta(seconds=duration_seconds) if started_at and duration_seconds is not None else None

    conn.execute(
        """
        INSERT INTO runs (
          id, version, environment, started_at, finished_at, total_scenarios,
          passed, failed, skipped, visibility, source_manifest_file, source_manifest_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            run_id,
            aliases.get(run_id),
            manifest.get("environment"),
            started_at,
            finished_at,
            manifest.get("totalScenarios"),
            manifest.get("passed"),
            manifest.get("failed"),
            manifest.get("skipped"),
            manifest.get("visibility", "internal"),
            source_file,
            source_hash,
        ],
    )

    imported_rows = 1
    for index, scenario in enumerate(manifest.get("scenarios", []) or [], start=1):
        scenario_uid, feature_file, feature_line, doors_number = insert_scenario_definition(
            conn,
            manifest,
            scenario,
            index,
            started_at,
        )
        screenshot_path, video_path = attachment_paths(scenario)
        attempts = scenario.get("attempts", []) or []
        jira_key = bug_lookup.get(doors_number, {}).get("jiraKey") if doors_number else None

        conn.execute(
            """
            INSERT INTO scenario_results (
              run_id, scenario_uid, name_at_run, status, duration_seconds, error_message,
              feature_file_at_run, feature_line_at_run, doors_number_at_run, jira_key_at_run,
              screenshot_path, video_path, retry_attempt, source_manifest_file, source_manifest_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                run_id,
                scenario_uid,
                scenario.get("name") or f"scenario-{index}",
                normalize_status(scenario.get("status")),
                parse_duration_seconds(scenario.get("duration")),
                first_error_message(scenario),
                feature_file,
                feature_line,
                doors_number,
                jira_key,
                screenshot_path,
                video_path,
                max(1, len(attempts)),
                source_file,
                source_hash,
            ],
        )
        imported_rows += 1

    record_import(conn, source_file, source_hash, "IMPORTED", imported_rows)
    return "imported", imported_rows


def backfill_jobs(dry_run=False):
    """For each existing run without a job, create a default job and worker_run record.

    Idempotent: safe to run multiple times — uses INSERT ... ON CONFLICT DO NOTHING.
    """
    conn = get_connection()
    init_schema(conn)

    rows = conn.execute("""
        SELECT r.id, r.version, r.environment, r.started_at, r.finished_at
        FROM runs r
        WHERE NOT EXISTS (
            SELECT 1 FROM worker_runs wr WHERE wr.run_id = r.id
        )
        ORDER BY r.started_at ASC
    """).fetchall()

    if not rows:
        print("No runs need job backfill.")
        return 0

    created = 0
    for run_id, version, environment, started_at, finished_at in rows:
        job_id = f"job-backfill-{run_id}"
        if dry_run:
            print(f"[DRY RUN] Would create job {job_id} for run {run_id}")
            continue

        conn.execute("""
            INSERT INTO jobs (
                job_id, version, environment, status, started_at, ended_at
            ) VALUES (?, ?, ?, 'completed', ?, ?)
            ON CONFLICT(job_id) DO NOTHING
        """, [job_id, version, environment, started_at, finished_at])

        conn.execute("""
            INSERT INTO worker_runs (
                worker_id, job_id, run_id, status, started_at, ended_at
            ) VALUES (?, ?, ?, 'completed', ?, ?)
            ON CONFLICT(worker_id) DO NOTHING
        """, [f"wr-backfill-{run_id}", job_id, run_id, started_at, finished_at])
        created += 1

    conn.close()
    print(f"Backfill complete: created {created} job(s).")
    return created


def backfill_scenario_history(conn):
    rows = conn.execute("""
        SELECT sr.doors_number_at_run, sr.scenario_uid, sr.name_at_run, sr.run_id,
               sr.status, sr.duration_seconds, r.version, r.started_at
        FROM scenario_results sr
        JOIN runs r ON sr.run_id = r.id
        WHERE sr.doors_number_at_run IS NOT NULL
        ORDER BY sr.doors_number_at_run, r.started_at
    """).fetchall()

    for row in rows:
        doors_number, scenario_uid, name, run_id, status, duration, version, started_at = row
        upsert_scenario_history(
            conn,
            doors_number=doors_number,
            scenario_uid=scenario_uid,
            name=name,
            run_id=run_id,
            status=status,
            version=version,
            timestamp=started_at,
        )


def migrate():
    conn = get_connection()
    init_schema(conn)

    aliases = load_aliases()
    bug_lookup = bug_mapping_lookup()
    summary = {"bug_mappings": 0, "imported": 0, "skipped": 0, "rows_imported": 0}

    conn.execute("BEGIN TRANSACTION")
    try:
        summary["bug_mappings"] = import_bug_tracker(conn)
        for manifest_path in sorted(MANIFESTS_DIR.glob("*.json")):
            status, rows = import_manifest(conn, manifest_path, aliases, bug_lookup)
            summary[status] += 1
            summary["rows_imported"] += rows
        backfill_scenario_history(conn)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    summary["runs"] = get_run_count(conn)
    summary["scenario_results"] = get_scenario_result_count(conn)
    summary["bug_mapping_rows"] = get_bug_mapping_count(conn)
    conn.close()
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate JSON manifests to DuckDB")
    parser.add_argument(
        "--backfill-jobs",
        action="store_true",
        help="Backfill job/worker_run records for existing runs without them",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without modifying data (use with --backfill-jobs)",
    )
    args = parser.parse_args()

    if args.backfill_jobs:
        backfill_jobs(dry_run=args.dry_run)
    else:
        result = migrate()
        print(
            "Migration complete: "
            f"runs={result['runs']} "
            f"scenario_results={result['scenario_results']} "
            f"bug_mappings={result['bug_mapping_rows']} "
            f"imported={result['imported']} "
            f"skipped={result['skipped']}"
        )
