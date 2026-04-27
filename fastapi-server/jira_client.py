import os
from typing import Optional

import httpx


class JiraClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        pat: Optional[str] = None,
        project: Optional[str] = None,
        issue_type: Optional[str] = None,
    ):
        self.base_url = (base_url or os.getenv("JIRA_BASE_URL", "")).rstrip("/")
        self.pat = pat or os.getenv("JIRA_PAT", "")
        self.project = project or os.getenv("JIRA_PROJECT", "")
        self.issue_type = issue_type or os.getenv("JIRA_ISSUE_TYPE", "Bug")
        self._ssl_verify = os.getenv("JIRA_SSL_VERIFY", "true").lower() != "false"

    def is_configured(self) -> bool:
        return bool(self.base_url and self.pat and self.project)

    def issue_url(self, key: str) -> str:
        return f"{self.base_url}/browse/{key}"

    def create_issue(self, summary: str, description: str) -> str:
        if not self.is_configured():
            raise RuntimeError(
                "Jira not configured. Set JIRA_BASE_URL, JIRA_PAT, JIRA_PROJECT."
            )

        payload = {
            "fields": {
                "project": {"key": self.project},
                "summary": summary,
                "description": description,
                "issuetype": {"name": self.issue_type},
            }
        }

        response = httpx.post(
            f"{self.base_url}/rest/api/2/issue",
            json=payload,
            headers={
                "Authorization": f"Bearer {self.pat}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30.0,
            verify=self._ssl_verify,
        )
        response.raise_for_status()
        return response.json()["key"]
