"""Shared Jira presentation helpers.

The failure-description template was duplicated between the manifest-based bug
route and the DuckDB-based triage route. Keeping it here lets both routers share
one source of truth (and survives the future split into separate route modules).
"""


def build_jira_description(
    run_id: str,
    scenario_name: str,
    doors_number: str | None,
    version: str | None,
    error_message: str | None,
    step_lines: str,
    duration: object | None = None,
) -> str:
    """Render the wiki-markup description for an automated-failure Jira issue.

    ``duration`` is optional; when ``None`` the Duration line is omitted (the
    triage path has no per-scenario duration, the manifest path does).
    """
    duration_line = f"*Duration:* {duration}\n" if duration is not None else ""
    return (
        f"h2. Automated Test Failure\n\n"
        f"*Run ID:* {run_id}\n"
        f"*Scenario:* {scenario_name}\n"
        f"*DOORS Number:* {doors_number or 'N/A'}\n"
        f"*Affects Version/s:* {version or 'N/A'}\n"
        f"{duration_line}"
        f"*Error:* {error_message or 'N/A'}\n\n"
        f"h3. Steps\n{{noformat}}\n{step_lines or 'N/A'}\n{{noformat}}"
    )
