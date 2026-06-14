"""Shared Allure/manifest result parsing.

Single home for the result-parsing logic that used to be duplicated between
server.py (_parse_allure_result / the parsing half of _save_results_to_duckdb)
and migrate_json_to_duckdb.py. This module is intentionally free of any
`server` import so the migration script can use it standalone.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

DOORS_TAG_RE = re.compile(r"@?(DOORS-\d+|ABS-\d+)", re.IGNORECASE)
EXPLICIT_ID_TAG_RE = re.compile(r"@?id:(.+)", re.IGNORECASE)


# ── Allure result-file parsing (used by the live test runner) ────────────────

def parse_allure_result(result_file: Path) -> dict | None:
    """Parse a single Allure result JSON file and extract full metadata."""
    try:
        data = json.loads(result_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    # Extract status
    raw_status = str(data.get("status", "unknown")).lower()
    status_map = {
        "passed": "PASSED",
        "failed": "FAILED",
        "broken": "BROKEN",
        "skipped": "SKIPPED",
        "unknown": "UNKNOWN",
    }
    status = status_map.get(raw_status, "UNKNOWN")

    name = data.get("name") or "unknown"
    full_name = data.get("fullName") or ""
    feature_file = full_name.split(":", 1)[0].split(".", 1)[0] if full_name else ""

    time_data = data.get("time") or {}
    duration = (time_data.get("duration") or 0) / 1000
    error = ((data.get("statusDetails") or {}).get("message") or "")[:500]
    identity_key = data.get("historyId") or f"{feature_file}:{name}"

    # Parse labels for tags (mimics Java AllureResultsParser.parseTags)
    labels = data.get("labels") or []
    tags = []
    doors_id = None
    dependencies = []
    for label in labels:
        if not isinstance(label, dict):
            continue
        label_name = label.get("name") or ""
        label_value = label.get("value") or ""
        if label_name == "tag":
            tag_str = str(label_value).strip()
            doors_match = re.search(r"@?(?:DOORS-\d+|ABS-\d+)", tag_str, re.IGNORECASE)
            if doors_match:
                doors_id = doors_match.group(0).lstrip("@")
            else:
                dep_match = re.match(r"@dep:(.+)", tag_str, re.IGNORECASE)
                if dep_match:
                    dependencies.append(dep_match.group(1).strip())
                else:
                    tags.append(tag_str)
        elif label_name == "suite":
            pass

    retry_attempt = 1
    history_id = data.get("historyId") or ""
    retry_match = re.search(r"--retry-(\d+)", history_id)
    if not retry_match:
        retry_match = re.search(r"--retry-(\d+)", name)
    if retry_match:
        retry_attempt = int(retry_match.group(1))

    # Timestamp from Allure start time
    start_ts = data.get("start")
    ts_str = datetime.fromtimestamp(start_ts / 1000).isoformat() if start_ts else datetime.now().isoformat()

    # Build AttemptResult
    attempt = {"status": raw_status, "timestamp": ts_str, "errorMessage": error or None}

    # Parse steps (Cucumber BDD steps from Allure result)
    raw_steps = data.get("steps") or []
    steps = []
    for st in raw_steps:
        step_error = ((st.get("statusDetails") or {}).get("message") or "")[:300]
        steps.append({
            "name": st.get("name") or "",
            "status": (st.get("status") or "unknown").lower(),
            "errorMessage": step_error or None,
        })

    return {
        "identity_key": identity_key,
        "name": name,
        "status": status,
        "status_raw": raw_status,
        "duration": duration,
        "error": error,
        "feature_file": feature_file,
        "tags": tags,
        "doors_id": doors_id,
        "dependencies": dependencies,
        "retry_attempt": retry_attempt,
        "attempt": attempt,
        "steps": steps,
        "start_ts_ms": start_ts or 0,
    }


def collect_scenarios(allure_dir: Path, started_at: datetime | None = None) -> list[dict]:
    """Parse all Allure result files in *allure_dir* and group them into scenarios.

    Groups results by identity_key to detect retries (multiple attempts).
    Only includes files whose start timestamp is within the current run window to
    avoid mixing results from previous Maven invocations that weren't cleaned up.
    The window is: [started_at - 5 min, now+1 min]. If started_at is unknown we
    use a generous 24-hour window anchored at the newest file's timestamp.
    """
    grouped: dict[str, list[dict]] = {}
    all_scenarios = []

    if allure_dir.exists():
        all_parsed = []
        for result_file in sorted(allure_dir.glob("*-result.json")):
            parsed = parse_allure_result(result_file)
            if parsed is not None:
                all_parsed.append(parsed)

        # Determine the run window anchor
        if all_parsed:
            newest_ts_ms = max(p["start_ts_ms"] for p in all_parsed)
            if started_at:
                window_start_ms = int(started_at.timestamp() * 1000) - 5 * 60 * 1000
            else:
                # No known start time — take only files within 24 h of the newest file
                window_start_ms = newest_ts_ms - 24 * 3600 * 1000
            window_end_ms = newest_ts_ms + 60 * 1000

            for parsed in all_parsed:
                ts = parsed["start_ts_ms"]
                if ts == 0 or window_start_ms <= ts <= window_end_ms:
                    key = parsed["identity_key"]
                    if key not in grouped:
                        grouped[key] = []
                    grouped[key].append(parsed)

    # Build scenarios list with attempt tracking
    scenario_map: dict[str, dict] = {}
    for key, attempts in grouped.items():
        # Sort by retry_attempt then timestamp
        attempts_sorted = sorted(attempts, key=lambda a: (a["retry_attempt"], a["attempt"]["timestamp"]))
        final = attempts_sorted[-1]

        # Flaky = final passed but earlier attempt failed
        is_flaky = False
        if final["status"] == "PASSED" and len(attempts_sorted) > 1:
            is_flaky = any(a["status_raw"] in ("failed", "broken") for a in attempts_sorted[:-1])

        # Build attempt list (only include when >1 or is_flaky to avoid clutter)
        attempt_list = []
        if is_flaky or len(attempts_sorted) > 1:
            attempt_list = [a["attempt"] for a in attempts_sorted]

        scenario_uid = hashlib.sha256(str(key).encode()).hexdigest()[:32]

        scenario_map[key] = {
            "uid": scenario_uid,
            "identity_key": key,
            "name": final["name"],
            "status": final["status"],
            "duration": final["duration"],
            "error": final["error"],
            "feature_file": final["feature_file"],
            "tags": final["tags"],
            "doors_id": final["doors_id"],
            "dependencies": final["dependencies"],
            "retry_attempt": final["retry_attempt"],
            "is_flaky": is_flaky,
            "attempt_list": attempt_list,
            "total_attempts": len(attempts_sorted),
            "steps": final["steps"],
        }
        all_scenarios.append(scenario_map[key])

    return all_scenarios


# ── Manifest scenario parsing (used by migrate_json_to_duckdb.py) ────────────

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
