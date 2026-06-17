import os
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")

from unittest.mock import patch

from server import app, create_token
from fastapi.testclient import TestClient

client = TestClient(app)


def _auth_headers():
    token = create_token("admin")
    return {"Authorization": f"Bearer {token}"}


def test_versions_endpoint():
    resp = client.get("/api/versions", headers=_auth_headers())

    assert resp.status_code == 200
    assert "versions" in resp.json()


def test_metrics_endpoint():
    resp = client.get("/api/dashboard/metrics", headers=_auth_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert "success_rate" in data
    assert "total_runs" in data


def test_home_dashboard_returns_html():
    resp = client.get("/", headers=_auth_headers())

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]

def test_metrics_version_breakdown_respects_version_filter():
    """Regression: the version bar-chart breakdown must honor the version filter."""
    import duckdb
    from datetime import datetime
    from db import init_schema, NonClosingConnectionWrapper
    import server as srv

    conn = duckdb.connect(":memory:")
    init_schema(conn)
    for rid, ver, passed in [("r1", "v1", 5), ("r2", "v2", 8)]:
        conn.execute(
            "INSERT INTO runs (id, version, environment, started_at, finished_at, "
            "total_scenarios, passed, failed, skipped) VALUES (?, ?, 'staging', ?, ?, ?, ?, 0, 0)",
            [rid, ver, datetime.now(), datetime.now(), passed, passed],
        )
    conn.commit()
    wrapped = NonClosingConnectionWrapper(conn)

    with patch.object(srv, "get_connection", lambda read_only=False: wrapped):
        resp = client.get(
            "/api/dashboard/metrics", params={"version": "v1"}, headers=_auth_headers()
        )
    conn.close()

    assert resp.status_code == 200
    versions = [vb["version"] for vb in resp.json()["version_breakdown"]]
    assert versions == ["v1"]  # v2 excluded by the version filter
