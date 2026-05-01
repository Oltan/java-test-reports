import os

import duckdb


DB_PATH = os.getenv("REPORTS_DUCKDB_PATH", "reports.duckdb")


def get_connection(read_only=False):
    conn = duckdb.connect(DB_PATH, read_only=read_only)
    return conn


def init_schema(conn):
    """Create all 6 tables + indexes if they don't exist."""
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

    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_version ON runs(version);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_version_started_at ON runs(version, started_at);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_results_run_id ON scenario_results(run_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_results_scenario_uid ON scenario_results(scenario_uid);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_results_status ON scenario_results(status);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_results_doors_number ON scenario_results(doors_number_at_run);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_results_scenario_run ON scenario_results(scenario_uid, run_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bug_mappings_jira_key ON bug_mappings(jira_key);")


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
