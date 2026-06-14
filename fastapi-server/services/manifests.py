"""Manifest load/write helpers and run-alias storage.

All manifest JSON writing funnels through write_manifest_file() so there is a
single write path.

Monkeypatch compatibility contract: tests patch attributes on the `server`
module (e.g. server.MANIFESTS_DIR, server.get_connection). Every such name is
therefore resolved through `import server` at call time — never captured via
`from server import X` at import time.
"""

import json
import threading
from datetime import datetime
from pathlib import Path

from models import RunManifest, TestRunOptions

_aliases_lock = threading.Lock()


def _load_aliases() -> dict:
    import server

    if not server.RUN_ALIASES_FILE.exists():
        return {}
    with _aliases_lock:
        return json.loads(server.RUN_ALIASES_FILE.read_text())


def _save_aliases(data: dict) -> None:
    import server

    with _aliases_lock:
        server.RUN_ALIASES_FILE.write_text(json.dumps(data, indent=2))


def get_run_alias(run_id: str) -> str:
    return _load_aliases().get(run_id, run_id)


def load_manifests() -> list[RunManifest]:
    import server

    if not server.MANIFESTS_DIR.exists():
        return []
    manifests = []
    for f in sorted(server.MANIFESTS_DIR.glob("*.json")):
        with open(f) as fh:
            data = json.load(fh)
        manifests.append(RunManifest.model_validate(data))
    return manifests


def write_manifest_file(manifest_path: Path, manifest: dict) -> None:
    """Single write path for manifest JSON files."""
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))


def write_manifest_json(run_id: str, options: TestRunOptions, scenarios: list, passed: int, failed: int, skipped: int, ts: datetime, effective_version: str = "") -> None:
    """Write the manifest for a completed test run (full scenario metadata)."""
    import server

    manifest_dir = server.PROJECT_ROOT / "manifests"
    manifest_dir.mkdir(exist_ok=True)
    manifest_path = manifest_dir / f"{run_id}.json"
    total = len(scenarios)
    manifest = {
        "runId": run_id,
        "timestamp": ts.isoformat(),
        "totalScenarios": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "duration": "0.0s",
        "version": effective_version or options.version or "",
        "environment": options.environment or "",
        "scenarios": [
            {
                "id": f"{run_id}-{i}",
                "name": s["name"],
                "status": s["status"].lower(),
                "duration": f"{s['duration']:.1f}s",
                "doorsAbsNumber": s.get("doors_id"),
                "tags": s.get("tags", []),
                "steps": s.get("steps", []),
                "attachments": [],
                "attempts": s.get("attempt_list", []),
                "dependencies": s.get("dependencies", []),
                "is_flaky": s.get("is_flaky", False),
                "errorMessage": s.get("error") or "",
            }
            for i, s in enumerate(scenarios)
        ],
    }
    write_manifest_file(manifest_path, manifest)


def sync_runs() -> dict:
    """Backfill both data stores:
    - Manifest files without a DuckDB row → insert into DuckDB
    - DuckDB runs without a manifest file → create manifest JSON
    Safe to call repeatedly (skips already-synced entries).
    """
    import hashlib

    import server

    manifests = load_manifests()
    manifest_by_id = {m.runId: m for m in manifests}

    _status_down = {"PASSED": "passed", "FAILED": "failed", "SKIPPED": "skipped",
                    "BROKEN": "failed", "UNKNOWN": "skipped"}

    conn = server.get_connection(read_only=False)
    try:
        server.init_schema(conn)
        db_runs = {r[0]: {"version": r[1], "environment": r[2], "started_at": r[3],
                          "finished_at": r[4], "total": r[5], "passed": r[6],
                          "failed": r[7], "skipped": r[8]}
                   for r in conn.execute(
                       "SELECT id, version, environment, started_at, finished_at, "
                       "total_scenarios, passed, failed, skipped FROM runs"
                   ).fetchall()}

        inserted_to_db = 0
        created_manifests = 0

        # 1. Manifests → DuckDB
        for run_id, m in manifest_by_id.items():
            if run_id not in db_runs:
                ts = m.timestamp or datetime.now()
                conn.execute(
                    """INSERT INTO runs (id, version, environment, started_at, finished_at,
                       total_scenarios, passed, failed, skipped, visibility)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'internal')""",
                    [run_id, m.version or None, m.environment or None,
                     ts, ts, m.totalScenarios, m.passed, m.failed, m.skipped],
                )
                for i, s in enumerate(m.scenarios):
                    uid = hashlib.sha256(f"{run_id}:{s.name}:{i}".encode()).hexdigest()[:32]
                    if not conn.execute(
                        "SELECT 1 FROM scenario_definitions WHERE scenario_uid = ?", [uid]
                    ).fetchone():
                        conn.execute(
                            """INSERT INTO scenario_definitions
                               (scenario_uid, identity_source, identity_key, current_name,
                                first_seen_run_id, last_seen_run_id, first_seen_at, last_seen_at)
                               VALUES (?, 'manifest', ?, ?, ?, ?, ?, ?)""",
                            [uid, f"{run_id}:{s.name}", s.name, run_id, run_id, ts, ts],
                        )
                    conn.execute(
                        """INSERT INTO scenario_results
                           (run_id, scenario_uid, name_at_run, status, duration_seconds,
                            error_message, feature_file_at_run, doors_number_at_run)
                           VALUES (?, ?, ?, ?, ?, ?, '', ?)""",
                        [run_id, uid, s.name, s.status.upper(), 0.0, None,
                         s.doorsAbsNumber or None],
                    )
                inserted_to_db += 1

        # 2. DuckDB → manifests (create new + refresh existing ones with empty scenario tags)
        for run_id, run_data in db_runs.items():
            existing = manifest_by_id.get(run_id)
            needs_tag_refresh = existing and existing.scenarios and not any(
                s.tags for s in existing.scenarios
            )
            if run_id not in manifest_by_id or needs_tag_refresh:
                scenario_rows = conn.execute(
                    "SELECT name_at_run, status, duration_seconds, error_message, "
                    "COALESCE(feature_file_at_run, '') "
                    "FROM scenario_results WHERE run_id = ? ORDER BY id",
                    [run_id],
                ).fetchall()
                ts = run_data["started_at"] or (existing.timestamp if existing else datetime.now())
                ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                total = run_data["total"] or len(scenario_rows)
                scenarios = [
                    {"id": f"{run_id}-{i}", "name": row[0],
                     "status": _status_down.get(row[1], "skipped"),
                     "duration": f"{(row[2] or 0):.1f}s",
                     "doorsAbsNumber": None,
                     "tags": [row[4]] if row[4] else [],
                     "steps": [], "attachments": [], "attempts": [], "dependencies": [],
                     "errorMessage": row[3] or ""}
                    for i, row in enumerate(scenario_rows)
                ]
                manifest_data = {
                    "runId": run_id,
                    "timestamp": ts_str,
                    "totalScenarios": total,
                    "passed": run_data["passed"] or 0,
                    "failed": run_data["failed"] or 0,
                    "skipped": run_data["skipped"] or 0,
                    "duration": existing.duration if existing else "0.0s",
                    "version": run_data["version"] or (existing.version if existing else "") or "",
                    "environment": run_data["environment"] or (existing.environment if existing else "") or "",
                    "scenarios": scenarios,
                }
                manifest_path = server.MANIFESTS_DIR / f"{run_id}.json"
                write_manifest_file(manifest_path, manifest_data)
                if run_id not in manifest_by_id:
                    created_manifests += 1
    finally:
        conn.close()

    return {"inserted_to_db": inserted_to_db, "created_manifests": created_manifests}
