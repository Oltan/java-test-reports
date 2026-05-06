import json
import os
import hashlib
import time
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

from atlassian import Jira  # type: ignore[reportMissingImports]


T = TypeVar("T")

DRY_RUN_ENV = "DRY_RUN"
DRY_RUN_TRUE_VALUES = {"1", "true", "yes", "on"}
DRY_RUN_JIRA_RESULT_ENV = "JIRA_DRY_RUN_RESULT"


def is_dry_run_enabled() -> bool:
    return os.getenv(DRY_RUN_ENV, "false").lower() in DRY_RUN_TRUE_VALUES


class JiraClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        pat: Optional[str] = None,
        project: Optional[str] = None,
        issue_type: Optional[str] = None,
        dry_run: Optional[bool] = None,
        retry_count: Optional[int] = None,
    ):
        self.url = (base_url or os.getenv("JIRA_URL") or os.getenv("JIRA_BASE_URL", "")).rstrip("/")
        self.pat = pat or os.getenv("JIRA_PAT", "")
        self.project_key = project or os.getenv("JIRA_PROJECT_KEY") or os.getenv("JIRA_PROJECT", "")
        self.issue_type = issue_type or os.getenv("JIRA_ISSUE_TYPE", "Bug")
        self.dry_run = (
            is_dry_run_enabled() or os.getenv("JIRA_DRY_RUN", "false").lower() in DRY_RUN_TRUE_VALUES
            if dry_run is None
            else dry_run
        )
        self.retry_count = retry_count if retry_count is not None else int(os.getenv("JIRA_RETRY_COUNT", "3"))
        self.jira = Jira(url=self.url, token=self.pat) if not self.dry_run and self.url and self.pat else None
        self._dry_run_issues: dict[str, dict[str, str]] = {}
        if self.dry_run:
            mock_path = Path(__file__).parent / "mock_jira.json"
            if mock_path.exists():
                self._dry_run_issues.update(json.loads(mock_path.read_text()))

    def is_configured(self) -> bool:
        return self.dry_run or bool(self.url and self.pat and self.project_key)

    def issue_url(self, key: str | dict[str, Any]) -> str:
        issue_key = key.get("key", "") if isinstance(key, dict) else key
        if self.dry_run:
            return f"https://dry-run.local/browse/{issue_key}"
        return f"{self.url}/browse/{issue_key}"

    def create_issue(
        self,
        summary: str,
        description: str,
        doors_number: Optional[str] = None,
    ) -> dict[str, str]:
        """Create Jira bug with wiki-renderer description."""
        if self.dry_run:
            if os.getenv(DRY_RUN_JIRA_RESULT_ENV, "success").lower() == "failure":
                raise RuntimeError("Jira dry-run failure requested")
            issue = self._dry_run_issue(summary, description, doors_number)
            self._dry_run_issues[issue["key"]] = issue
            return issue
        self._require_configuration()

        fields: dict[str, Any] = {
            "project": {"key": self.project_key},
            "summary": summary,
            "description": description,
            "issuetype": {"name": self.issue_type},
        }
        if doors_number:
            fields["DOORS Number"] = doors_number

        jira = self._active_jira()
        result = self._with_retry(lambda: jira.create_issue(fields=fields))
        return {
            "key": result["key"],
            "status": result.get("fields", {}).get("status", {}).get("name", "Created"),
        }

    def search_by_doors_number(self, doors_number: str) -> list[dict[str, str]]:
        """Find existing Jira issues by DOORS number (custom field)."""
        if self.dry_run:
            if os.getenv(DRY_RUN_JIRA_RESULT_ENV, "success").lower() == "failure":
                raise RuntimeError("Jira dry-run failure requested")
            return [
                {"key": issue["key"], "status": issue["status"]}
                for issue in self._dry_run_issues.values()
                if issue.get("doors_number") == doors_number
            ]
        self._require_configuration()

        jql = f'project = {self.project_key} AND "DOORS Number" ~ "{doors_number}"'
        jira = self._active_jira()
        result = self._with_retry(lambda: jira.jql(jql))
        return [
            {"key": issue["key"], "status": issue["fields"]["status"]["name"]}
            for issue in result.get("issues", [])
        ]

    def get_issue_status(self, issue_key: str) -> str:
        if self.dry_run:
            return "Open"
        self._require_configuration()

        jira = self._active_jira()
        issue = self._with_retry(lambda: jira.issue(issue_key))
        return issue["fields"]["status"]["name"]

    def add_comment(self, issue_key: str, comment: str) -> bool:
        if self.dry_run:
            if os.getenv(DRY_RUN_JIRA_RESULT_ENV, "success").lower() == "failure":
                raise RuntimeError("Jira dry-run failure requested")
            return True
        self._require_configuration()

        jira = self._active_jira()
        self._with_retry(lambda: jira.issue_add_comment(issue_key, comment))
        return True

    def attach_screenshot(self, issue_key: str, filepath: str) -> bool:
        if self.dry_run:
            if os.getenv(DRY_RUN_JIRA_RESULT_ENV, "success").lower() == "failure":
                raise RuntimeError("Jira dry-run failure requested")
            return True
        self._require_configuration()

        jira = self._active_jira()
        self._with_retry(lambda: jira.add_attachment(issue_key, filepath))
        return True

    def _require_configuration(self) -> None:
        if not self.is_configured() or self.jira is None:
            raise RuntimeError(
                "Jira not configured. Set JIRA_URL/JIRA_BASE_URL, JIRA_PAT, and JIRA_PROJECT_KEY/JIRA_PROJECT."
            )

    def _active_jira(self) -> Any:
        self._require_configuration()
        return self.jira

    def _with_retry(self, operation: Callable[[], T]) -> T:
        last_error: Exception | None = None
        attempts = max(1, self.retry_count)
        for attempt in range(attempts):
            try:
                return operation()
            except Exception as exc:
                last_error = exc
                if attempt == attempts - 1:
                    break
                time.sleep(0.5 * (2**attempt))
        raise last_error  # type: ignore[misc]

    def _dry_run_issue(
        self,
        summary: str,
        description: str,
        doors_number: Optional[str],
    ) -> dict[str, str]:
        source = "\n".join([summary, description, doors_number or ""])
        scenario_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        key = f"DRY-{scenario_hash[:8]}"
        return {
            "key": key,
            "status": "Dry Run",
            "url": self.issue_url(key),
            "doors_number": doors_number or "",
        }
