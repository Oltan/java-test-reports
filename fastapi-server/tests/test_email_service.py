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