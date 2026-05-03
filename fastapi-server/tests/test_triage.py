import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")

import server
from server import app, create_token

TEST_MANIFESTS_DIR = Path(__file__).parent.parent / "manifests"
server.MANIFESTS_DIR = TEST_MANIFESTS_DIR

client = TestClient(app)

RUN_ID = "test-001"
FAILED_SCENARIO_ID = "sc-fail-001"


def _auth_headers() -> dict:
    token = create_token("admin")
    return {"Authorization": f"Bearer {token}"}


def test_triage_page_returns_html_with_auth():
    response = client.get(f"/reports/{RUN_ID}/triage", headers=_auth_headers())
    assert response.status_code == 200
    html = response.text
    assert "Failure Analysis" in html
    assert 'data-testid="failure-card"' not in html or "triage-main" in html


def test_triage_page_requires_auth():
    response = client.get(f"/reports/{RUN_ID}/triage")
    assert response.status_code in (401, 403)


def test_create_jira_bug_returns_jira_key():
    with patch.object(server.jira_client, "is_configured", return_value=True), \
         patch.object(server.jira_client, "create_issue", return_value="PROJ-123"), \
         patch.object(server.jira_client, "issue_url", return_value="https://jira.example.com/browse/PROJ-123"):
        response = client.post(
            f"/api/v1/runs/{RUN_ID}/scenarios/{FAILED_SCENARIO_ID}/jira",
            headers=_auth_headers(),
        )

    assert response.status_code == 201
    data = response.json()
    assert data["jiraKey"] == "PROJ-123"
    assert data["jiraUrl"] == "https://jira.example.com/browse/PROJ-123"


def test_create_jira_bug_returns_503_when_not_configured():
    with patch.object(server.jira_client, "is_configured", return_value=False):
        response = client.post(
            f"/api/v1/runs/{RUN_ID}/scenarios/{FAILED_SCENARIO_ID}/jira",
            headers=_auth_headers(),
        )
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"].lower()


def test_triage_api_requires_auth():
    response = client.get(f"/api/triage/{RUN_ID}")
    assert response.status_code in (401, 403)


def test_override_requires_reason():
    response = client.post(
        f"/api/triage/{RUN_ID}/scenarios/{FAILED_SCENARIO_ID}/override",
        json={"decision": "accepted_pass", "reason": ""},
        headers=_auth_headers(),
    )
    assert response.status_code == 422


def test_override_requires_valid_decision():
    response = client.post(
        f"/api/triage/{RUN_ID}/scenarios/{FAILED_SCENARIO_ID}/override",
        json={"decision": "invalid", "reason": "some reason"},
        headers=_auth_headers(),
    )
    assert response.status_code == 422