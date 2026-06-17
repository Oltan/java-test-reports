"""Bug / Jira routes, split out of server.py.

Shared state, helpers, models and dependencies are referenced via the ``server``
module (``server.X``) rather than imported by value, so the test monkeypatch
surface (``server.get_connection``, ``server.jira_client`` …) is preserved and
there is no import cycle (server includes these routers after it is fully
defined).
"""
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

import server
from jira_client import JiraClient

router = APIRouter()


@router.post(
    "/api/v1/runs/{run_id}/scenarios/{scenario_id}/jira",
    response_model=server.JiraResponse,
    status_code=201,
    dependencies=[Depends(server.verify_token)],
)
def create_jira_bug(run_id: str, scenario_id: str):
    manifests = server.load_manifests()
    manifest = next((m for m in manifests if m.runId == run_id), None)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    scenario = next((s for s in manifest.scenarios if s.id == scenario_id), None)
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")

    if not server.jira_client.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Jira integration not configured. Set JIRA_BASE_URL, JIRA_PAT, JIRA_PROJECT.",
        )

    summary = f"Automated test failed: {scenario.name}"
    step_lines = "\n".join(
        f"  [FAIL] {s.name}" if s.status == "failed" else f"  [pass] {s.name}"
        for s in scenario.steps
    )
    failed_step = next((s for s in scenario.steps if s.status == "failed"), None)
    error_message = failed_step.errorMessage if failed_step and failed_step.errorMessage else "N/A"
    description = server.build_jira_description(
        run_id=run_id,
        scenario_name=scenario.name,
        doors_number=scenario.doorsAbsNumber,
        version=manifest.version,
        error_message=error_message,
        step_lines=step_lines,
        duration=scenario.duration,
    )

    try:
        issue = server.jira_client.create_issue(summary, description)
        key = issue["key"] if isinstance(issue, dict) else issue
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Jira API error {exc.response.status_code}: {exc.response.text[:300]}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Jira error: {str(exc)}",
        )

    return server.JiraResponse(jiraKey=key, jiraUrl=server.jira_client.issue_url(key))


@router.get("/api/v1/bugs", dependencies=[Depends(server.verify_token)])
def list_bugs():
    return server.tracker.get_all()


@router.get("/api/v1/bugs/{doors_number}", dependencies=[Depends(server.verify_token)])
def get_bug(doors_number: str):
    mapping = server.tracker.get(doors_number)
    if mapping is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No mapping found for DOORS number: {doors_number}",
        )
    return mapping


@router.post(
    "/api/v1/bugs/{doors_number}/create",
    response_model=server.BugCreateResponse,
    status_code=201,
    dependencies=[Depends(server.verify_token)],
)
def create_bug(doors_number: str, req: server.BugCreateRequest, _: server.TokenData = Depends(server.verify_token)):
    if os.getenv("DRY_RUN", "false").lower() not in {"1", "true", "yes", "on"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Fake Jira bug creation is available only when DRY_RUN is enabled.",
        )

    existing = server.tracker.get(doors_number)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=existing)
    issue = JiraClient(dry_run=True).create_issue(
        req.scenarioName,
        f"Dry-run bug mapping for run {req.runId} and DOORS item {doors_number}.",
        doors_number,
    )
    jira_key = issue["key"]
    server.tracker.register(doors_number, jira_key, req.scenarioName, req.runId)
    return server.BugCreateResponse(jiraKey=jira_key, doorsNumber=doors_number)
