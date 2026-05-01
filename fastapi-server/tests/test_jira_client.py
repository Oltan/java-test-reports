from unittest.mock import Mock, patch

import pytest

from jira_client import JiraClient


def test_dry_run_returns_static_results(monkeypatch):
    monkeypatch.setenv("JIRA_DRY_RUN", "true")

    client = JiraClient()

    assert client.is_configured()
    assert client.create_issue("summary", "h2. wiki") == {
        "key": "DRY-RUN-001",
        "status": "Dry Run",
    }
    assert client.search_by_doors_number("DR-1") == []
    assert client.get_issue_status("DRY-RUN-001") == "Open"
    assert client.add_comment("DRY-RUN-001", "comment") is True
    assert client.attach_screenshot("DRY-RUN-001", "/tmp/screenshot.png") is True


def test_create_issue_uses_atlassian_with_wiki_renderer_description(monkeypatch):
    monkeypatch.delenv("JIRA_DRY_RUN", raising=False)
    jira = Mock()
    jira.create_issue.return_value = {
        "key": "BUG-123",
        "fields": {"status": {"name": "Open"}},
    }

    with patch("jira_client.Jira", return_value=jira) as jira_class:
        client = JiraClient(base_url="https://jira.local/", pat="pat", project="BUG")
        result = client.create_issue("Failed scenario", "h2. Failure", "DOORS-42")

    jira_class.assert_called_once_with(url="https://jira.local", token="pat")
    jira.create_issue.assert_called_once_with(
        fields={
            "project": {"key": "BUG"},
            "summary": "Failed scenario",
            "description": "h2. Failure",
            "issuetype": {"name": "Bug"},
            "DOORS Number": "DOORS-42",
        }
    )
    assert result == {"key": "BUG-123", "status": "Open"}


def test_search_status_comment_and_attachment_use_atlassian(monkeypatch):
    monkeypatch.delenv("JIRA_DRY_RUN", raising=False)
    jira = Mock()
    jira.jql.return_value = {
        "issues": [{"key": "BUG-1", "fields": {"status": {"name": "In Progress"}}}]
    }
    jira.issue.return_value = {"fields": {"status": {"name": "Done"}}}

    with patch("jira_client.Jira", return_value=jira):
        client = JiraClient(base_url="https://jira.local", pat="pat", project="BUG")
        assert client.search_by_doors_number("DOORS-42") == [
            {"key": "BUG-1", "status": "In Progress"}
        ]
        assert client.get_issue_status("BUG-1") == "Done"
        assert client.add_comment("BUG-1", "wiki comment") is True
        assert client.attach_screenshot("BUG-1", "/tmp/failure.png") is True

    jira.jql.assert_called_once_with('project = BUG AND "DOORS Number" ~ "DOORS-42"')
    jira.issue.assert_called_once_with("BUG-1")
    jira.issue_add_comment.assert_called_once_with("BUG-1", "wiki comment")
    jira.add_attachment.assert_called_once_with("BUG-1", "/tmp/failure.png")


def test_retry_replays_transient_failures(monkeypatch):
    monkeypatch.delenv("JIRA_DRY_RUN", raising=False)
    monkeypatch.setattr("jira_client.time.sleep", lambda _: None)
    jira = Mock()
    jira.create_issue.side_effect = [
        RuntimeError("temporary"),
        {"key": "BUG-2", "fields": {"status": {"name": "Open"}}},
    ]

    with patch("jira_client.Jira", return_value=jira):
        client = JiraClient(
            base_url="https://jira.local",
            pat="pat",
            project="BUG",
            retry_count=2,
        )
        assert client.create_issue("summary", "description") == {
            "key": "BUG-2",
            "status": "Open",
        }

    assert jira.create_issue.call_count == 2


def test_retry_raises_after_configured_attempts(monkeypatch):
    monkeypatch.delenv("JIRA_DRY_RUN", raising=False)
    monkeypatch.setattr("jira_client.time.sleep", lambda _: None)
    jira = Mock()
    jira.issue.side_effect = RuntimeError("still failing")

    with patch("jira_client.Jira", return_value=jira):
        client = JiraClient(
            base_url="https://jira.local",
            pat="pat",
            project="BUG",
            retry_count=2,
        )
        with pytest.raises(RuntimeError, match="still failing"):
            client.get_issue_status("BUG-1")

    assert jira.issue.call_count == 2
