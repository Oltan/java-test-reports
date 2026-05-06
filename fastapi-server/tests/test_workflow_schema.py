from datetime import datetime

import duckdb
import pytest

from db import init_schema


def _fresh_conn():
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    init_schema(conn)
    return conn


def _constraint_columns(conn, table_name, constraint_type):
    return [
        tuple(row[0])
        for row in conn.execute(
            """
            SELECT constraint_column_names
            FROM duckdb_constraints()
            WHERE table_name = ? AND constraint_type = ?
            """,
            [table_name, constraint_type],
        ).fetchall()
    ]


def _insert_legacy_run(conn, run_id="run-001"):
    conn.execute(
        """
        INSERT INTO runs (
          id, version, environment, started_at, finished_at, total_scenarios,
          passed, failed, skipped, visibility, source_manifest_file, source_manifest_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            run_id,
            "1.0.0",
            "staging",
            datetime(2026, 5, 3, 10, 0, 0),
            datetime(2026, 5, 3, 10, 1, 0),
            1,
            0,
            1,
            0,
            "internal",
            "manifest.json",
            "hash-001",
        ],
    )


def test_workflow_schema_init_is_idempotent_and_preserves_legacy_tables():
    conn = _fresh_conn()

    table_names = {
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM duckdb_tables() WHERE schema_name = 'main' AND NOT internal"
        ).fetchall()
    }
    assert {
        "runs",
        "scenario_definitions",
        "scenario_results",
        "bug_mappings",
        "migration_imports",
        "pipeline_status",
        "jobs",
        "worker_runs",
        "triage_decisions",
        "jira_mappings",
        "override_audit",
        "public_snapshots",
    }.issubset(table_names)

    indexes = {row[0] for row in conn.execute("SELECT index_name FROM duckdb_indexes()").fetchall()}
    assert {
        "idx_worker_runs_job_id",
        "idx_worker_runs_run_id",
        "idx_triage_decisions_run_id",
        "idx_triage_decisions_decision",
        "idx_jira_mappings_jira_key",
        "idx_override_audit_scenario_uid",
        "idx_public_snapshots_job_id",
    }.issubset(indexes)

    assert ("job_id",) in _constraint_columns(conn, "jobs", "PRIMARY KEY")
    assert ("worker_id",) in _constraint_columns(conn, "worker_runs", "PRIMARY KEY")
    assert ("scenario_uid", "jira_key") in _constraint_columns(conn, "jira_mappings", "UNIQUE")

    _insert_legacy_run(conn)
    conn.execute(
        """
        INSERT INTO scenario_definitions (
          scenario_uid, identity_source, identity_key, current_name, current_feature_file,
          current_feature_line, doors_number, first_seen_run_id, last_seen_run_id,
          first_seen_at, last_seen_at, active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            "scenario-001",
            "manifest-id",
            "scenario-001",
            "Legacy scenario",
            "features/login.feature",
            12,
            "ABS-12345",
            "run-001",
            "run-001",
            datetime(2026, 5, 3, 10, 0, 0),
            datetime(2026, 5, 3, 10, 0, 0),
            True,
        ],
    )
    conn.execute(
        """
        INSERT INTO scenario_results (
          run_id, scenario_uid, name_at_run, status, duration_seconds,
          error_message, feature_file_at_run, feature_line_at_run, doors_number_at_run,
          jira_key_at_run, screenshot_path, video_path, retry_attempt,
          source_manifest_file, source_manifest_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            "run-001",
            "scenario-001",
            "Legacy scenario",
            "FAILED",
            12.5,
            "failure",
            "features/login.feature",
            12,
            "ABS-12345",
            "QA-1",
            "screenshots/failure.png",
            "videos/failure.mp4",
            2,
            "manifest.json",
            "hash-001",
        ],
    )
    result_count = conn.execute("SELECT COUNT(*) FROM scenario_results WHERE run_id = 'run-001'").fetchone()
    assert result_count is not None
    assert result_count[0] == 1


def test_triage_jira_and_override_audit_workflow_rows_round_trip():
    conn = _fresh_conn()
    _insert_legacy_run(conn, "run-002")

    conn.execute(
        """
        INSERT INTO jobs (
          job_id, requester, tags, retry_count, parallel, environment,
          version, status, started_at, ended_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            "job-001",
            "qa.lead",
            "@smoke,@critical",
            1,
            2,
            "staging",
            "1.0.0",
            "completed",
            datetime(2026, 5, 3, 9, 59, 0),
            datetime(2026, 5, 3, 10, 2, 0),
        ],
    )
    conn.execute(
        """
        INSERT INTO worker_runs (
          worker_id, job_id, run_id, shard, status, output_dir, started_at, ended_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            "worker-001",
            "job-001",
            "run-002",
            0,
            "completed",
            "target/allure-results/shard-0",
            datetime(2026, 5, 3, 10, 0, 0),
            datetime(2026, 5, 3, 10, 1, 0),
        ],
    )
    conn.execute(
        """
        INSERT INTO triage_decisions (
          scenario_uid, run_id, decision, actor, reason, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            "scenario-002",
            "run-002",
            "jira_created",
            "qa.lead",
            "new regression needs tracking",
            datetime(2026, 5, 3, 10, 5, 0),
        ],
    )
    conn.execute(
        """
        INSERT INTO jira_mappings (scenario_uid, doors_id, jira_key, created_at)
        VALUES (?, ?, ?, ?)
        """,
        ["scenario-002", "ABS-12346", "QA-123", datetime(2026, 5, 3, 10, 5, 1)],
    )
    with pytest.raises(duckdb.ConstraintException):
        conn.execute(
            """
            INSERT INTO jira_mappings (scenario_uid, doors_id, jira_key, created_at)
            VALUES (?, ?, ?, ?)
            """,
            ["scenario-002", "ABS-12346", "QA-123", datetime(2026, 5, 3, 10, 5, 2)],
        )
    conn.execute(
        """
        INSERT INTO override_audit (
          scenario_uid, previous_status, new_decision, reason, actor, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            "scenario-002",
            "FAILED",
            "accepted_skip",
            "known external dependency outage",
            "qa.lead",
            datetime(2026, 5, 3, 10, 6, 0),
        ],
    )
    conn.execute(
        """
        INSERT INTO public_snapshots (
          share_id, job_id, created_by, created_at, snapshot_data, status
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            "share-001",
            "job-001",
            "qa.lead",
            datetime(2026, 5, 3, 10, 7, 0),
            '{"summary":{"failed":1}}',
            "active",
        ],
    )

    triage = conn.execute(
        """
        SELECT scenario_uid, run_id, decision, actor, reason, timestamp
        FROM triage_decisions
        WHERE scenario_uid = 'scenario-002'
        """
    ).fetchone()
    assert triage == (
        "scenario-002",
        "run-002",
        "jira_created",
        "qa.lead",
        "new regression needs tracking",
        datetime(2026, 5, 3, 10, 5, 0),
    )

    audit = conn.execute(
        """
        SELECT id, scenario_uid, previous_status, new_decision, reason, actor, timestamp
        FROM override_audit
        WHERE scenario_uid = 'scenario-002'
        """
    ).fetchone()
    assert audit == (
        1,
        "scenario-002",
        "FAILED",
        "accepted_skip",
        "known external dependency outage",
        "qa.lead",
        datetime(2026, 5, 3, 10, 6, 0),
    )
