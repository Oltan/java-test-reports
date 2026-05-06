import os
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import doors_service
import email_service
import server
from bug_tracker import BugTracker
from jira_client import JiraClient


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {server.create_token('admin')}"}


@pytest.fixture
def temp_tracker():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.write(fd, b'{"version": "1.0", "mappings": {}}')
    os.close(fd)
    yield BugTracker(path)
    Path(path).unlink(missing_ok=True)


def test_jira_dry_run_returns_deterministic_key_and_duplicate(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.delenv("JIRA_DRY_RUN_RESULT", raising=False)

    client = JiraClient()
    first = client.create_issue("Login failure", "h2. Failure", "DOORS-100")
    second = client.create_issue("Login failure", "h2. Failure", "DOORS-100")

    assert first["key"] == second["key"]
    assert re.fullmatch(r"DRY-[0-9a-f]{8}", first["key"])
    assert first["url"] == f"https://dry-run.local/browse/{first['key']}"
    assert client.search_by_doors_number("DOORS-100") == [
        {"key": first["key"], "status": "Dry Run"}
    ]


def test_jira_dry_run_failure(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("JIRA_DRY_RUN_RESULT", "failure")

    with pytest.raises(RuntimeError, match="Jira dry-run failure requested"):
        JiraClient().create_issue("Login failure", "h2. Failure", "DOORS-101")


def test_fake_bug_endpoint_rejects_when_dry_run_false(client, monkeypatch, temp_tracker):
    monkeypatch.setenv("DRY_RUN", "false")

    with patch("server.tracker", temp_tracker):
        response = client.post(
            "/api/v1/bugs/DOORS-200/create",
            headers=_auth_headers(),
            json={"scenarioName": "Login Test", "runId": "run-200"},
        )

    assert response.status_code == 403
    assert "DRY_RUN" in response.json()["detail"]
    assert temp_tracker.get("DOORS-200") is None


def test_fake_bug_endpoint_uses_dry_key_when_dry_run_true(client, monkeypatch, temp_tracker):
    monkeypatch.setenv("DRY_RUN", "true")

    with patch("server.tracker", temp_tracker):
        response = client.post(
            "/api/v1/bugs/DOORS-201/create",
            headers=_auth_headers(),
            json={"scenarioName": "Login Test", "runId": "run-201"},
        )

    assert response.status_code == 201
    data = response.json()
    assert re.fullmatch(r"DRY-[0-9a-f]{8}", data["jiraKey"])
    assert temp_tracker.get("DOORS-201")["jiraKey"] == data["jiraKey"]


def test_doors_dry_run_success_and_failure(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.delenv("DOORS_DRY_RUN_RESULT", raising=False)

    assert doors_service.is_doors_available() is True
    assert doors_service.run_doors_dxl("export requirements") == (
        0,
        "DOORS dry-run export completed",
        "",
    )

    monkeypatch.setenv("DOORS_DRY_RUN_RESULT", "failure")
    code, stdout, stderr = doors_service.run_doors_dxl("export requirements")
    assert code == 1
    assert stdout == ""
    assert "failure requested" in stderr


def test_email_dry_run_captures_public_share_link_and_failure(monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.delenv("EMAIL_DRY_RUN_RESULT", raising=False)
    email_service.DRY_RUN_OUTBOX.clear()

    public_link = "https://reports.example.test/reports/run-300"
    assert email_service.send_email(
        "qa@example.test",
        "Dry report",
        "test_report.html",
        {
            "total": 1,
            "passed": 0,
            "failed": 1,
            "skipped": 0,
            "started_at": "2026-05-03T00:00:00Z",
            "dashboard_url": public_link,
        },
    ) is True

    assert email_service.DRY_RUN_OUTBOX[-1]["to"] == "qa@example.test"
    assert public_link in email_service.DRY_RUN_OUTBOX[-1]["body"]

    monkeypatch.setenv("EMAIL_DRY_RUN_RESULT", "failure")
    with pytest.raises(RuntimeError, match="Email dry-run failure requested"):
        email_service.send_email(
            "qa@example.test",
            "Dry report",
            "test_report.html",
            {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "started_at": "",
                "dashboard_url": public_link,
            },
        )
