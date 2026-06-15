"""Tests for the run lifecycle work (bug #6): pid/exit_code persistence,
the FIFO queue + concurrency limit, duplicate-run guard, and restart recovery.

These exercise the orchestration logic directly against an in-memory DuckDB and
a monkeypatched spawn seam, so no real Maven process is ever started.
"""
from datetime import datetime
from unittest.mock import patch

import duckdb
import pytest

from db import init_schema, NonClosingConnectionWrapper


@pytest.fixture
def in_mem_db():
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    yield NonClosingConnectionWrapper(conn)
    conn.close()


def _insert_worker(conn, job_id="job-1", run_id="test-1", status="running"):
    now = datetime.now()
    conn.execute(
        "INSERT INTO jobs (job_id, tags, environment, status, started_at) VALUES (?, ?, ?, ?, ?)",
        [job_id, "@smoke", "staging", status, now],
    )
    conn.execute(
        "INSERT INTO worker_runs (worker_id, job_id, run_id, shard, status, started_at) VALUES (?, ?, ?, ?, ?, ?)",
        [f"{job_id}-w0", job_id, run_id, 0, status, now],
    )
    conn.commit()


# ── 6A: process-identity persistence ─────────────────────────────────────────

def test_persist_worker_records_pid_and_exit_code(in_mem_db):
    import server as srv
    with patch.object(srv, "get_connection", lambda read_only=False: in_mem_db):
        _insert_worker(in_mem_db, run_id="test-pid")
        srv._persist_worker("test-pid", pid=4242, exit_code=0, last_output_at=datetime.now())

        row = in_mem_db.execute(
            "SELECT pid, exit_code, last_output_at FROM worker_runs WHERE run_id = ?",
            ["test-pid"],
        ).fetchone()
    assert row[0] == 4242
    assert row[1] == 0
    assert row[2] is not None


def test_persist_worker_ignores_unknown_columns(in_mem_db):
    import server as srv
    with patch.object(srv, "get_connection", lambda read_only=False: in_mem_db):
        _insert_worker(in_mem_db, run_id="test-safe")
        # Unknown keys must be silently dropped (no SQL injection / no crash).
        srv._persist_worker("test-safe", pid=7, status="hacked", bogus="x")

        row = in_mem_db.execute(
            "SELECT pid, status FROM worker_runs WHERE run_id = ?", ["test-safe"]
        ).fetchone()
    assert row[0] == 7
    assert row[1] == "running"  # status not in allow-list, unchanged
