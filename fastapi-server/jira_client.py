import os
import time
from typing import Any, Callable, Optional, TypeVar

from atlassian import Jira  # type: ignore[reportMissingImports]


T = TypeVar("T")


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
            os.getenv("JIRA_DRY_RUN", "false").lower() == "true"
            if dry_run is None
            else dry_run
        )
        self.retry_count = retry_count if retry_count is not None else int(os.getenv("JIRA_RETRY_COUNT", "3"))
        self.jira = Jira(url=self.url, token=self.pat) if not self.dry_run and self.url and self.pat else None

    def is_configured(self) -> bool:
        return self.dry_run or bool(self.url and self.pat and self.project_key)

    def issue_url(self, key: str | dict[str, Any]) -> str:
        issue_key = key.get("key", "") if isinstance(key, dict) else key
        return f"{self.url}/browse/{issue_key}"

    def create_issue(
        self,
        summary: str,
        description: str,
        doors_number: Optional[str] = None,
    ) -> dict[str, str]:
        """Create Jira bug with wiki-renderer description."""
        if self.dry_run:
            return {"key": "DRY-RUN-001", "status": "Dry Run"}
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
            return []
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
            return True
        self._require_configuration()

        jira = self._active_jira()
        self._with_retry(lambda: jira.issue_add_comment(issue_key, comment))
        return True

    def attach_screenshot(self, issue_key: str, filepath: str) -> bool:
        if self.dry_run:
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
