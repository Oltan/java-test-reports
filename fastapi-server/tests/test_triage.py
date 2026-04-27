import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")

import server
from server import app

TEST_MANIFESTS_DIR = Path(__file__).parent.parent / "manifests"
server.MANIFESTS_DIR = TEST_MANIFESTS_DIR

client = TestClient(app)

RUN_ID = "test-001"
FAILED_SCENARIO_ID = "sc-fail-001"


def test_triage_page_returns_html_with_scenario_names():
    response = client.get(f"/reports/{RUN_ID}/triage")
    assert response.status_code == 200
    html = response.text
    assert "Payment Checkout Failure" in html
    assert "User Login" not in html
    assert 'data-testid="failure-card"' in html
    assert 'data-testid="create-jira-button"' in html


def test_create_jira_bug_returns_jira_key():
    with patch.object(server.jira_client, "is_configured", return_value=True), \
         patch.object(server.jira_client, "create_issue", return_value="PROJ-123"), \
         patch.object(server.jira_client, "issue_url", return_value="https://jira.example.com/browse/PROJ-123"):
        response = client.post(f"/api/v1/runs/{RUN_ID}/scenarios/{FAILED_SCENARIO_ID}/jira")

    assert response.status_code == 201
    data = response.json()
    assert data["jiraKey"] == "PROJ-123"
    assert data["jiraUrl"] == "https://jira.example.com/browse/PROJ-123"


def test_create_jira_bug_returns_503_when_not_configured():
    with patch.object(server.jira_client, "is_configured", return_value=False):
        response = client.post(f"/api/v1/runs/{RUN_ID}/scenarios/{FAILED_SCENARIO_ID}/jira")
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"].lower()


def test_triage_button_click_flow():
    page = client.get(f"/reports/{RUN_ID}/triage")
    assert page.status_code == 200
    html = page.text
    assert FAILED_SCENARIO_ID in html
    assert "Create Jira Bug" in html

    with patch.object(server.jira_client, "is_configured", return_value=True), \
         patch.object(server.jira_client, "create_issue", return_value="PROJ-123"), \
         patch.object(server.jira_client, "issue_url", return_value="https://jira.example.com/browse/PROJ-123"):
        jira_response = client.post(f"/api/v1/runs/{RUN_ID}/scenarios/{FAILED_SCENARIO_ID}/jira")

    assert jira_response.status_code == 201
    jira_data = jira_response.json()
    assert jira_data["jiraKey"] == "PROJ-123"
    assert 'data-testid="jira-key-display"' in html
