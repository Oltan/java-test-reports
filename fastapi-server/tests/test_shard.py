"""Shard mode tests.

Includes a REAL test that runs `mvn ... -Dcucumber.execution.dry-run=true` to
discover scenarios (no browser needed) — skipped only if Maven is unavailable.
The rest are fast unit/integration tests with the spawn seam monkeypatched.
"""
import shutil
from datetime import datetime
from unittest.mock import patch

import duckdb
import pytest

from db import init_schema, NonClosingConnectionWrapper
from server import app, create_token
from fastapi.testclient import TestClient


def _auth():
    return {"Authorization": f"Bearer {create_token('admin')}"}


@pytest.fixture
def client():
    with TestClient(app, follow_redirects=False) as c:
        yield c


@pytest.fixture
def in_mem_db():
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    yield NonClosingConnectionWrapper(conn)
    conn.close()


# ── pure helpers ──────────────────────────────────────────────────────────────

def test_shard_features_round_robin():
    import server as srv
    assert srv._shard_features(["a.feature", "b.feature", "c.feature"], 2) == [
        ["a.feature", "c.feature"], ["b.feature"],
    ]
    assert srv._shard_features([], 3) == []
    # more shards than files -> capped at file count
    assert srv._shard_features(["a.feature"], 5) == [["a.feature"]]
    # dedup
    assert srv._shard_features(["a.feature", "a.feature", "b.feature"], 2) == [
        ["a.feature"], ["b.feature"],
    ]


def test_test_command_includes_features():
    import server as srv
    from models import TestRunOptions
    opts = TestRunOptions(tags="@smoke", features="f1.feature,f2.feature")
    cmd = srv._test_command(opts)
    assert "-Dcucumber.features=f1.feature,f2.feature" in cmd


# ── shard mode through the API (spawn + discovery mocked) ────────────────────

def test_shard_start_creates_per_shard_workers(client, in_mem_db):
    import server as srv
    spawned = []
    fake_scenarios = [
        {"name": "s1", "feature": "features/a.feature", "line": 3},
        {"name": "s2", "feature": "features/b.feature", "line": 5},
        {"name": "s3", "feature": "features/a.feature", "line": 9},
    ]
    with patch.object(srv, "get_connection", lambda read_only=False: in_mem_db), \
         patch.object(srv, "_spawn_run", lambda rid, opts, out: spawned.append((rid, opts.features))), \
         patch.object(srv, "TEST_MAX_CONCURRENCY", 1), \
         patch.object(srv, "_discover_scenarios", lambda tags: fake_scenarios):
        resp = client.post(
            "/api/tests/start",
            json={"mode": "shard", "parallel": 2, "tags": "@smoke", "environment": "staging"},
            headers=_auth(),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["parallel"] == 2  # 2 feature files -> 2 shards
    feats = sorted(in_mem_db.execute(
        "SELECT features FROM worker_runs WHERE job_id = ? ORDER BY shard", [body["job_id"]]
    ).fetchall())
    assert ("features/a.feature",) in feats
    assert ("features/b.feature",) in feats
    # both shards spawned with their own feature subset
    assert {f for _, f in spawned} == {"features/a.feature", "features/b.feature"}


def test_shard_mode_rejects_retry(client, in_mem_db):
    import server as srv
    with patch.object(srv, "get_connection", lambda read_only=False: in_mem_db), \
         patch.object(srv, "_spawn_run", lambda *a: None):
        resp = client.post(
            "/api/tests/start",
            json={"mode": "shard", "parallel": 2, "retry_count": 1},
            headers=_auth(),
        )
    assert resp.status_code == 422  # validator: shard incompatible with retry


# ── REAL Maven dry-run discovery (the live verification) ─────────────────────

@pytest.mark.skipif(
    shutil.which("mvn") is None and shutil.which("mvn.cmd") is None,
    reason="Maven not available",
)
def test_discovery_real_mvn():
    """Runs an actual `mvn ... dry-run` to discover scenarios from the real
    feature files — no browser involved."""
    import server as srv
    scenarios = srv._discover_scenarios("@smoke")
    assert scenarios, "dry-run discovered no scenarios"
    for s in scenarios:
        assert s["name"] and s["feature"].endswith(".feature") and isinstance(s["line"], int)
    # the checked-in login.feature must be among the discovered feature files
    assert any("login.feature" in s["feature"] for s in scenarios)
