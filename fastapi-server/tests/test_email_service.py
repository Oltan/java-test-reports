import os
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")

from unittest.mock import patch
from fastapi.testclient import TestClient
from server import app, create_token

client = TestClient(app)


def _auth_headers():
    token = create_token("admin")
    return {"Authorization": f"Bearer {token}"}


def test_email_send_endpoint_uses_mock_service():
    with patch("server.send_email", return_value=True) as send_email:
        resp = client.post(
            "/api/email/send",
            params={"to": "qa@example.com", "run_id": "run-001"},
            headers=_auth_headers(),
        )

    assert resp.status_code == 200
    assert resp.json() == {"sent": True}
    send_email.assert_called_once()
    to, subject, template, context = send_email.call_args.args
    assert to == "qa@example.com"
    assert subject == "Test Raporu - run-001"
    assert template == "test_report.html"
    assert context["dashboard_url"].endswith("/reports/run-001")


def test_email_send_endpoint_reports_mock_failure():
    with patch("server.send_email", side_effect=RuntimeError("SMTP offline")):
        resp = client.post(
            "/api/email/send",
            params={"to": "qa@example.com", "run_id": "run-002"},
            headers=_auth_headers(),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["sent"] is False
    assert "SMTP offline" in data["error"]

def test_email_send_uses_real_run_metrics():
    """Regression: context must carry the run's real totals, not hardcoded zeros."""
    import duckdb
    from datetime import datetime
    from db import init_schema, NonClosingConnectionWrapper
    import server as srv

    conn = duckdb.connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO runs (id, version, environment, started_at, finished_at, "
        "total_scenarios, passed, failed, skipped) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["run-xyz", "1.0", "staging", datetime.now(), datetime.now(), 10, 7, 2, 1],
    )
    conn.commit()
    wrapped = NonClosingConnectionWrapper(conn)

    with patch.object(srv, "get_connection", lambda read_only=False: wrapped), \
         patch("server.send_email", return_value=True) as send_email:
        resp = client.post(
            "/api/email/send",
            params={"to": "qa@example.com", "run_id": "run-xyz"},
            headers=_auth_headers(),
        )
    conn.close()

    assert resp.status_code == 200
    _, _, _, context = send_email.call_args.args
    assert (context["total"], context["passed"], context["failed"], context["skipped"]) == (10, 7, 2, 1)
    assert context["started_at"]
