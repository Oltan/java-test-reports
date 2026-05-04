import json
import os

import duckdb


DB_PATH = os.getenv("REPORTS_DUCKDB_PATH", "reports.duckdb")


def get_connection(read_only=False):
    conn = duckdb.connect(DB_PATH, read_only=read_only)
    return conn


class NonClosingConnectionWrapper:
    """Wraps a DuckDB connection so close() is a no-op.

    Server-side code calls conn.close() after each request.
    When a test fixture supplies the connection, close() would
    invalidate the fixture's connection object, causing subsequent
    tests to fail with 'Connection already closed!'.
    """

    def __init__(self, conn):
        object.__setattr__(self, "_conn", conn)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_conn"), name)

    def close(self):
        pass  # no-op to prevent server closing test fixture connection

    def __enter__(self):
        return object.__getattribute__(self, "_conn").__enter__()

    def __exit__(self, *args):
        pass  # no-op so fixture connection stays open


def init_schema(conn):
    """Create reporting and workflow tables + indexes if they don't exist."""
    conn.execute("""
    CREATE TABLE IF NOT EXISTS runs (
      id TEXT PRIMARY KEY,
      version TEXT,
      environment TEXT,
      started_at TIMESTAMP,
      finished_at TIMESTAMP,
      total_scenarios INTEGER,
      passed INTEGER,
      failed INTEGER,
      skipped INTEGER,
      visibility TEXT DEFAULT 'internal',
      source_manifest_file TEXT,
      source_manifest_hash TEXT,
      imported_at TIMESTAMP DEFAULT current_timestamp
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS scenario_definitions (
      scenario_uid TEXT PRIMARY KEY,
      identity_source TEXT NOT NULL,
      identity_key TEXT NOT NULL,
      current_name TEXT,
      current_feature_file TEXT,
      current_feature_line INTEGER,
      doors_number TEXT,
      first_seen_run_id TEXT,
      last_seen_run_id TEXT,
      first_seen_at TIMESTAMP,
      last_seen_at TIMESTAMP,
      active BOOLEAN DEFAULT true
    );
    """)

    conn.execute("CREATE SEQUENCE IF NOT EXISTS scenario_result_id_seq START 1;")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS scenario_results (
      id BIGINT PRIMARY KEY DEFAULT nextval('scenario_result_id_seq'),
      run_id TEXT NOT NULL REFERENCES runs(id),
      scenario_uid TEXT REFERENCES scenario_definitions(scenario_uid),
      name_at_run TEXT NOT NULL,
      status TEXT NOT NULL CHECK (status IN ('PASSED', 'FAILED', 'SKIPPED', 'BROKEN', 'UNKNOWN')),
      duration_seconds DOUBLE,
      error_message TEXT,
      feature_file_at_run TEXT,
      feature_line_at_run INTEGER,
      doors_number_at_run TEXT,
      jira_key_at_run TEXT,
      screenshot_path TEXT,
      video_path TEXT,
      retry_attempt INTEGER DEFAULT 1,
      source_manifest_file TEXT,
      source_manifest_hash TEXT,
      imported_at TIMESTAMP DEFAULT current_timestamp
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS bug_mappings (
      doors_number TEXT PRIMARY KEY,
      jira_key TEXT NOT NULL,
      jira_status TEXT,
      source TEXT DEFAULT 'bug-tracker.json',
      first_seen_at TIMESTAMP DEFAULT current_timestamp,
      updated_at TIMESTAMP DEFAULT current_timestamp
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS migration_imports (
      id TEXT PRIMARY KEY,
      source_file TEXT NOT NULL,
      source_hash TEXT NOT NULL,
      status TEXT NOT NULL,
      started_at TIMESTAMP,
      finished_at TIMESTAMP,
      rows_imported INTEGER,
      error_message TEXT
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS pipeline_status (
      run_id TEXT REFERENCES runs(id),
      stage TEXT NOT NULL,
      status TEXT NOT NULL,
      started_at TIMESTAMP,
      finished_at TIMESTAMP,
      error_message TEXT,
      PRIMARY KEY (run_id, stage)
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
      job_id TEXT PRIMARY KEY,
      requester TEXT,
      tags TEXT,
      retry_count INTEGER,
      parallel INTEGER,
      environment TEXT,
      version TEXT,
      status TEXT,
      started_at TIMESTAMP,
      ended_at TIMESTAMP
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS worker_runs (
      worker_id TEXT PRIMARY KEY,
      job_id TEXT REFERENCES jobs(job_id),
      run_id TEXT REFERENCES runs(id),
      shard INTEGER,
      status TEXT,
      output_dir TEXT,
      started_at TIMESTAMP,
      ended_at TIMESTAMP
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS triage_decisions (
      scenario_uid TEXT PRIMARY KEY,
      run_id TEXT REFERENCES runs(id),
      decision TEXT CHECK (decision IN ('needs_jira', 'jira_linked', 'jira_created', 'accepted_pass', 'accepted_skip')),
      actor TEXT,
      reason TEXT,
      timestamp TIMESTAMP
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS jira_mappings (
      scenario_uid TEXT,
      doors_id TEXT,
      jira_key TEXT,
      created_at TIMESTAMP,
      UNIQUE(scenario_uid, jira_key)
    );
    """)

    conn.execute("CREATE SEQUENCE IF NOT EXISTS override_audit_id_seq START 1;")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS override_audit (
      id INTEGER PRIMARY KEY DEFAULT nextval('override_audit_id_seq'),
      scenario_uid TEXT,
      previous_status TEXT,
      new_decision TEXT,
      reason TEXT,
      actor TEXT,
      timestamp TIMESTAMP
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS public_snapshots (
      share_id TEXT PRIMARY KEY,
      job_id TEXT REFERENCES jobs(job_id),
      created_by TEXT,
      created_at TIMESTAMP,
      snapshot_data TEXT,
      status TEXT
    );
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_version ON runs(version);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_version_started_at ON runs(version, started_at);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_results_run_id ON scenario_results(run_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_results_scenario_uid ON scenario_results(scenario_uid);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_results_status ON scenario_results(status);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_results_doors_number ON scenario_results(doors_number_at_run);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_results_scenario_run ON scenario_results(scenario_uid, run_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_results_scenario_status ON scenario_results(scenario_uid, status);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bug_mappings_jira_key ON bug_mappings(jira_key);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_started_at ON jobs(started_at);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_worker_runs_job_id ON worker_runs(job_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_worker_runs_run_id ON worker_runs(run_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_triage_decisions_run_id ON triage_decisions(run_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_triage_decisions_decision ON triage_decisions(decision);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jira_mappings_doors_id ON jira_mappings(doors_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jira_mappings_jira_key ON jira_mappings(jira_key);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_override_audit_scenario_uid ON override_audit(scenario_uid);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_override_audit_timestamp ON override_audit(timestamp);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_public_snapshots_job_id ON public_snapshots(job_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_public_snapshots_status ON public_snapshots(status);")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS scenario_history (
      doors_number TEXT PRIMARY KEY,
      scenario_uid TEXT,
      current_name TEXT,
      first_seen_at TIMESTAMP,
      last_seen_at TIMESTAMP,
      total_runs INTEGER DEFAULT 0,
      pass_count INTEGER DEFAULT 0,
      fail_count INTEGER DEFAULT 0,
      skip_count INTEGER DEFAULT 0,
      last_status TEXT,
      run_history JSON,
      updated_at TIMESTAMP DEFAULT current_timestamp
    );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scenario_history_uid ON scenario_history(scenario_uid);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scenario_history_last_seen ON scenario_history(last_seen_at);")


def fetch_all_dicts(conn, query, params=None):
    result = conn.execute(query, params or [])
    columns = [col[0] for col in result.description]
    return [dict(zip(columns, row)) for row in result.fetchall()]


def get_run_count(conn):
    return conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]


def get_scenario_result_count(conn):
    return conn.execute("SELECT COUNT(*) FROM scenario_results").fetchone()[0]


def get_bug_mapping_count(conn):
    return conn.execute("SELECT COUNT(*) FROM bug_mappings").fetchone()[0]


def upsert_scenario_history(conn, doors_number, scenario_uid, name, run_id, status, version, jira_keys=None, timestamp=None):
    """Upsert a scenario result into the history table.

    For PASSED tests, explanation is auto-generated: "{version} sürümünde test otomasyon ile doğrulanmıştır"
    For FAILED/BROKEN tests, explanation comes from Jira keys (if any).
    """
    if timestamp is None:
        timestamp = datetime.now()

    if status == "PASSED":
        explanation = f"{version or 'N/A'} sürümünde test otomasyon ile doğrulanmıştır"
    else:
        if jira_keys:
            explanation = ", ".join(jira_keys) if isinstance(jira_keys, (list, tuple)) else str(jira_keys)
        else:
            explanation = None

    existing = conn.execute(
        "SELECT run_history, pass_count, fail_count, skip_count, total_runs, first_seen_at FROM scenario_history WHERE doors_number = ?",
        [doors_number]
    ).fetchone()

    if existing:
        run_history = json.loads(existing[0]) if existing[0] else []
        pass_count = existing[1] + (1 if status == "PASSED" else 0)
        fail_count = existing[2] + (1 if status in ("FAILED", "BROKEN") else 0)
        skip_count = existing[3] + (1 if status == "SKIPPED" else 0)
        total_runs = existing[4] + 1
        first_seen_at = existing[5]

        run_entry = {
            "run_id": run_id,
            "status": status,
            "explanation": explanation,
            "timestamp": timestamp.isoformat(),
        }
        run_history.append(run_entry)

        conn.execute("""
            UPDATE scenario_history
            SET current_name = ?, last_seen_at = ?, total_runs = ?, pass_count = ?,
                fail_count = ?, skip_count = ?, last_status = ?, run_history = ?,
                updated_at = current_timestamp
            WHERE doors_number = ?
        """, [name, timestamp, total_runs, pass_count, fail_count, skip_count, status, json.dumps(run_history), doors_number])
    else:
        run_entry = {
            "run_id": run_id,
            "status": status,
            "explanation": explanation,
            "timestamp": timestamp.isoformat(),
        }
        run_history = [run_entry]
        pass_count = 1 if status == "PASSED" else 0
        fail_count = 1 if status in ("FAILED", "BROKEN") else 0
        skip_count = 1 if status == "SKIPPED" else 0

        conn.execute("""
            INSERT INTO scenario_history
            (doors_number, scenario_uid, current_name, first_seen_at, last_seen_at,
             total_runs, pass_count, fail_count, skip_count, last_status, run_history)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [doors_number, scenario_uid, name, timestamp, timestamp, 1,
              pass_count, fail_count, skip_count, status, json.dumps(run_history)])


def update_scenario_history_explanation(conn, doors_number, run_id, explanation):
    """Update the explanation for a specific run in scenario_history (e.g. after Jira creation)."""
    existing = conn.execute(
        "SELECT run_history FROM scenario_history WHERE doors_number = ?",
        [doors_number]
    ).fetchone()
    if not existing or not existing[0]:
        return False

    run_history = json.loads(existing[0])
    for entry in run_history:
        if entry.get("run_id") == run_id:
            entry["explanation"] = explanation
            break
    else:
        return False

    conn.execute("""
        UPDATE scenario_history
        SET run_history = ?, updated_at = current_timestamp
        WHERE doors_number = ?
    """, [json.dumps(run_history), doors_number])
    return True


def get_scenario_history(conn, doors_number=None):
    """Get scenario history. If doors_number provided, returns single row. Otherwise all rows."""
    if doors_number:
        row = conn.execute("""
            SELECT doors_number, scenario_uid, current_name, first_seen_at, last_seen_at,
                   total_runs, pass_count, fail_count, skip_count, last_status, run_history
            FROM scenario_history
            WHERE doors_number = ?
        """, [doors_number]).fetchone()
        if not row:
            return None
        return {
            "doors_number": row[0],
            "scenario_uid": row[1],
            "current_name": row[2],
            "first_seen_at": row[3],
            "last_seen_at": row[4],
            "total_runs": row[5],
            "pass_count": row[6],
            "fail_count": row[7],
            "skip_count": row[8],
            "last_status": row[9],
            "history": json.loads(row[10]) if row[10] else [],
        }
    else:
        rows = conn.execute("""
            SELECT doors_number, scenario_uid, current_name, first_seen_at, last_seen_at,
                   total_runs, pass_count, fail_count, skip_count, last_status, run_history
            FROM scenario_history
            ORDER BY last_seen_at DESC
        """).fetchall()
        return [{
            "doors_number": r[0],
            "scenario_uid": r[1],
            "current_name": r[2],
            "first_seen_at": r[3],
            "last_seen_at": r[4],
            "total_runs": r[5],
            "pass_count": r[6],
            "fail_count": r[7],
            "skip_count": r[8],
            "last_status": r[9],
            "history": json.loads(r[10]) if r[10] else [],
        } for r in rows]


def get_scenario_matrix(conn, limit=100, offset=0):
    """Return scenario history formatted as a matrix view for dashboard display."""
    rows = conn.execute("""
        SELECT doors_number, scenario_uid, current_name, total_runs, pass_count, fail_count, skip_count, last_status, run_history
        FROM scenario_history
        ORDER BY last_seen_at DESC
        LIMIT ? OFFSET ?
    """, [limit, offset]).fetchall()

    matrix = []
    for r in rows:
        run_history = json.loads(r[8]) if r[8] else []
        runs = {}
        for entry in run_history:
            runs[entry["run_id"]] = {
                "status": entry["status"],
                "explanation": entry.get("explanation"),
                "timestamp": entry["timestamp"],
            }

        matrix.append({
            "doors_number": r[0],
            "scenario_uid": r[1],
            "scenario_name": r[2],
            "total_runs": r[3],
            "pass_count": r[4],
            "fail_count": r[5],
            "skip_count": r[6],
            "last_status": r[7],
            "runs": runs,
        })
    return matrix
