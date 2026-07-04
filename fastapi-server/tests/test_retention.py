"""Tests for services/retention.py — per-run artifact cleanup policy.

Runs against an in-memory DuckDB and tmp_path artifact dirs; no server needed.
"""
from datetime import datetime, timedelta

import duckdb
import pytest

from db import init_schema, NonClosingConnectionWrapper
from services.retention import cleanup_run_artifacts

NOW = datetime(2026, 7, 4, 12, 0, 0)


@pytest.fixture
def in_mem_db():
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    yield NonClosingConnectionWrapper(conn)
    conn.close()


def _get_connection_for(db):
    return lambda read_only=False: db


def _add_worker_run(db, run_id, status, started_at):
    db.execute(
        "INSERT INTO worker_runs (worker_id, job_id, run_id, shard, status, output_dir, started_at) "
        "VALUES (?, ?, ?, 0, ?, '', ?)",
        [f"{run_id}-w0", f"job-{run_id}", run_id, status, started_at],
    )


def _make_artifacts(target_dir, manifests_dir, run_id):
    allure = target_dir / f"allure-results-{run_id}"
    allure.mkdir(parents=True)
    (allure / "x-result.json").write_text("{}")
    att = manifests_dir / run_id
    att.mkdir(parents=True)
    (att / "shot.png").write_bytes(b"png")
    return allure, att


@pytest.fixture
def dirs(tmp_path):
    target = tmp_path / "target"
    manifests = tmp_path / "manifests"
    target.mkdir()
    manifests.mkdir()
    return target, manifests


def test_old_terminal_run_removed_recent_kept(in_mem_db, dirs, monkeypatch):
    monkeypatch.setenv("RUN_RETENTION_DAYS", "30")
    monkeypatch.setenv("RUN_RETENTION_MAX_RUNS", "0")
    target, manifests = dirs
    old_dirs = _make_artifacts(target, manifests, "test-old")
    new_dirs = _make_artifacts(target, manifests, "test-new")
    _add_worker_run(in_mem_db, "test-old", "completed", NOW - timedelta(days=45))
    _add_worker_run(in_mem_db, "test-new", "completed", NOW - timedelta(days=1))

    summary = cleanup_run_artifacts(_get_connection_for(in_mem_db), target, manifests, now=NOW)

    assert summary["removed"] == ["test-old"]
    assert all(not p.exists() for p in old_dirs)
    assert all(p.exists() for p in new_dirs)
    # manifest JSONs / DB rows are never retention's business
    assert in_mem_db.execute("SELECT COUNT(*) FROM worker_runs").fetchone()[0] == 2


def test_active_runs_never_touched(in_mem_db, dirs, monkeypatch):
    monkeypatch.setenv("RUN_RETENTION_DAYS", "30")
    target, manifests = dirs
    running_dirs = _make_artifacts(target, manifests, "test-run")
    queued_dirs = _make_artifacts(target, manifests, "test-que")
    _add_worker_run(in_mem_db, "test-run", "running", NOW - timedelta(days=90))
    _add_worker_run(in_mem_db, "test-que", "queued", NOW - timedelta(days=90))

    summary = cleanup_run_artifacts(_get_connection_for(in_mem_db), target, manifests, now=NOW)

    assert summary["removed"] == []
    assert all(p.exists() for p in [*running_dirs, *queued_dirs])


def test_max_runs_cap_removes_oldest_beyond_cap(in_mem_db, dirs, monkeypatch):
    monkeypatch.setenv("RUN_RETENTION_DAYS", "0")  # age rule off, cap only
    monkeypatch.setenv("RUN_RETENTION_MAX_RUNS", "2")
    target, manifests = dirs
    for i, rid in enumerate(["test-a", "test-b", "test-c", "test-d"]):
        _make_artifacts(target, manifests, rid)
        _add_worker_run(in_mem_db, rid, "completed", NOW - timedelta(days=i))

    summary = cleanup_run_artifacts(_get_connection_for(in_mem_db), target, manifests, now=NOW)

    # newest two (test-a, test-b) kept; older two removed
    assert sorted(summary["removed"]) == ["test-c", "test-d"]
    assert (target / "allure-results-test-a").exists()
    assert (target / "allure-results-test-b").exists()
    assert not (target / "allure-results-test-c").exists()
    assert not (manifests / "test-d").exists()


def test_disabled_when_both_zero(in_mem_db, dirs, monkeypatch):
    monkeypatch.setenv("RUN_RETENTION_DAYS", "0")
    monkeypatch.setenv("RUN_RETENTION_MAX_RUNS", "0")
    target, manifests = dirs
    _make_artifacts(target, manifests, "test-ancient")
    _add_worker_run(in_mem_db, "test-ancient", "completed", NOW - timedelta(days=999))

    summary = cleanup_run_artifacts(_get_connection_for(in_mem_db), target, manifests, now=NOW)

    assert summary["disabled"] is True
    assert (target / "allure-results-test-ancient").exists()


def test_unknown_dir_falls_back_to_mtime(in_mem_db, dirs, monkeypatch):
    monkeypatch.setenv("RUN_RETENTION_DAYS", "30")
    target, manifests = dirs
    allure, att = _make_artifacts(target, manifests, "test-ghost")  # no DB row
    old_ts = (NOW - timedelta(days=60)).timestamp()
    import os
    for p in [allure, allure / "x-result.json", att, att / "shot.png"]:
        os.utime(p, (old_ts, old_ts))

    summary = cleanup_run_artifacts(_get_connection_for(in_mem_db), target, manifests, now=NOW)

    assert summary["removed"] == ["test-ghost"]
    assert not allure.exists() and not att.exists()


def test_db_failure_degrades_to_mtime_only(dirs, monkeypatch):
    monkeypatch.setenv("RUN_RETENTION_DAYS", "30")
    target, manifests = dirs
    allure, att = _make_artifacts(target, manifests, "test-x")
    old_ts = (NOW - timedelta(days=60)).timestamp()
    import os
    for p in [allure, allure / "x-result.json", att, att / "shot.png"]:
        os.utime(p, (old_ts, old_ts))

    def broken_connection(read_only=False):
        raise RuntimeError("db locked")

    summary = cleanup_run_artifacts(broken_connection, target, manifests, now=NOW)

    assert summary["removed"] == ["test-x"]
