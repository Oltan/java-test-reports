import os
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")

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