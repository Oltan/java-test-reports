"""Tests for the run lifecycle work (bug #6): pid/exit_code persistence,
the FIFO queue + concurrency limit, duplicate-run guard, and restart recovery.

These exercise the orchestration logic directly against an in-memory DuckDB and
a monkeypatched spawn seam, so no real Maven process is ever started.
"""
from datetime import datetime
from contextlib import ExitStack
from unittest.mock import patch

import duckdb
import pytest
from fastapi.testclient import TestClient

from db import init_schema, NonClosingConnectionWrapper
from server import app, create_token


def _auth():
    return {"Authorization": f"Bearer {create_token('admin')}"}


@pytest.fixture
def in_mem_db():
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    yield NonClosingConnectionWrapper(conn)
    conn.close()


@pytest.fixture
def client():
    with TestClient(app, follow_redirects=False) as c:
        yield c


def _patched(in_mem_db, spawned, max_concurrency=1):
    """Patch the DB, the spawn seam (records run_ids), and the concurrency limit."""
    import server as srv
    stack = ExitStack()
    stack.enter_context(patch.object(srv, "get_connection", lambda read_only=False: in_mem_db))
    stack.enter_context(patch.object(srv, "_spawn_run", lambda rid, opts, out: spawned.append(rid)))
    stack.enter_context(patch.object(srv, "TEST_MAX_CONCURRENCY", max_concurrency))
    return stack


def _start(client, tags="@smoke", force=False):
    return client.post(
        "/api/tests/start",
        json={"tags": tags, "retry_count": 0, "browser": "chrome",
              "parallel": 1, "environment": "staging", "version": "1.0.0", "force": force},
        headers=_auth(),
    )


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


# ── 6B: concurrency limit + FIFO queue ───────────────────────────────────────

def test_second_job_queues_when_at_capacity(client, in_mem_db):
    spawned = []
    with _patched(in_mem_db, spawned, max_concurrency=1):
        r1 = _start(client, tags="@smoke")
        r2 = _start(client, tags="@regression")

    assert r1.status_code == 200 and r1.json()["status"] == "started"
    assert r2.status_code == 200 and r2.json()["status"] == "queued"
    # Only the first job's run was spawned; the queued one was not.
    assert r1.json()["runs"][0] in spawned
    assert r2.json()["runs"][0] not in spawned

    j2 = in_mem_db.execute(
        "SELECT status FROM jobs WHERE job_id = ?", [r2.json()["job_id"]]
    ).fetchone()
    assert j2[0] == "queued"


def test_dispatch_promotes_queued_job_when_capacity_frees(client, in_mem_db):
    spawned = []
    with _patched(in_mem_db, spawned, max_concurrency=1):
        r1 = _start(client, tags="@smoke")
        r2 = _start(client, tags="@regression")
        assert r2.json()["status"] == "queued"

        # First job finishes -> capacity frees.
        in_mem_db.execute(
            "UPDATE jobs SET status = 'completed' WHERE job_id = ?", [r1.json()["job_id"]]
        )
        in_mem_db.commit()

        import server as srv
        started = srv._dispatch_queued()

    assert r2.json()["job_id"] in started
    j2 = in_mem_db.execute(
        "SELECT status FROM jobs WHERE job_id = ?", [r2.json()["job_id"]]
    ).fetchone()
    assert j2[0] == "running"
    assert r2.json()["runs"][0] in spawned


# ── 6C: duplicate-run guard (409 + force) ────────────────────────────────────

def test_duplicate_active_run_returns_409(client, in_mem_db):
    spawned = []
    with _patched(in_mem_db, spawned, max_concurrency=2):
        r1 = _start(client, tags="@smoke")
        r2 = _start(client, tags="@smoke")  # same tags+environment, still active

    assert r1.status_code == 200
    assert r2.status_code == 409
    assert "force" in r2.json()["detail"].lower()


def test_force_bypasses_duplicate_guard(client, in_mem_db):
    spawned = []
    with _patched(in_mem_db, spawned, max_concurrency=2):
        r1 = _start(client, tags="@smoke")
        r2 = _start(client, tags="@smoke", force=True)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["job_id"] != r2.json()["job_id"]


# ── 6D: restart orphan recovery (interrupted) ────────────────────────────────

def test_recover_orphans_marks_running_as_interrupted(in_mem_db):
    import server as srv
    with patch.object(srv, "get_connection", lambda read_only=False: in_mem_db):
        _insert_worker(in_mem_db, job_id="job-stale", run_id="run-stale", status="running")
        n = srv._recover_orphans()  # pid is NULL -> no kill attempted

    assert n == 1
    w = in_mem_db.execute(
        "SELECT status, ended_at FROM worker_runs WHERE run_id = ?", ["run-stale"]
    ).fetchone()
    j = in_mem_db.execute(
        "SELECT status FROM jobs WHERE job_id = ?", ["job-stale"]
    ).fetchone()
    assert w[0] == "interrupted" and w[1] is not None
    assert j[0] == "interrupted"


def test_recover_orphans_noop_when_nothing_running(in_mem_db):
    import server as srv
    with patch.object(srv, "get_connection", lambda read_only=False: in_mem_db):
        _insert_worker(in_mem_db, job_id="job-done", run_id="run-done", status="completed")
        n = srv._recover_orphans()

    assert n == 0
    j = in_mem_db.execute("SELECT status FROM jobs WHERE job_id = ?", ["job-done"]).fetchone()
    assert j[0] == "completed"  # untouched


def test_maybe_kill_stale_is_pid_reuse_safe():
    import server as srv
    # None and an almost-certainly-unrelated/nonexistent pid must not raise.
    srv._maybe_kill_stale(None)
    srv._maybe_kill_stale(2_000_000_000)


# ── 6E: stall / hard-timeout watchdog ────────────────────────────────────────

def test_abort_reason_hard_and_stall_and_none():
    import server as srv
    with patch.object(srv, "RUN_HARD_TIMEOUT", 100), patch.object(srv, "RUN_STALL_TIMEOUT", 30):
        assert srv._abort_reason(elapsed=101, idle=1) == "hard timeout"
        assert srv._abort_reason(elapsed=50, idle=31) == "stalled (no output)"
        assert srv._abort_reason(elapsed=50, idle=10) is None


def test_abort_reason_zero_timeout_disables_check():
    import server as srv
    with patch.object(srv, "RUN_HARD_TIMEOUT", 0), patch.object(srv, "RUN_STALL_TIMEOUT", 0):
        assert srv._abort_reason(elapsed=10_000, idle=10_000) is None


def test_terminate_proc_falls_back_to_kill(monkeypatch):
    import server as srv
    from unittest.mock import MagicMock
    proc = MagicMock()
    proc.pid = 2_000_000_000  # not a real process group -> getpgid raises
    srv._terminate_proc(proc)
    proc.kill.assert_called_once()


# ── 6F: WebSocket lifecycle state events ─────────────────────────────────────

def test_broadcast_state_message_shape():
    import asyncio
    import server as srv
    sent = []

    async def rec(run_id, message):
        sent.append((run_id, message))

    with patch.object(srv.ws_manager, "broadcast", rec):
        asyncio.run(srv._broadcast_state("run-x", "completed", exit_code=0))

    assert sent == [("run-x", {"type": "state", "run_id": "run-x", "status": "completed", "exit_code": 0})]


def test_start_broadcasts_initial_state(client, in_mem_db):
    import server as srv
    spawned = []
    sent = []

    async def rec(run_id, message):
        sent.append(message)

    with _patched(in_mem_db, spawned, max_concurrency=1):
        with patch.object(srv.ws_manager, "broadcast", rec):
            r = _start(client, tags="@smoke")

    assert r.status_code == 200
    states = [m for m in sent if m.get("type") == "state"]
    assert states and states[0]["status"] == "started" or states[0]["status"] == "running"
