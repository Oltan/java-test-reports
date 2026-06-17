"""Run-listing, run-detail, rename and scenario-history/matrix routes.

Split out of server.py; shared state/helpers referenced as server.X to keep the
test monkeypatch surface (server.get_connection, …) intact.
"""
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

import server
from models import RunManifest, ScenarioResult

router = APIRouter()


@router.get("/api/v1/runs", response_model=List[RunManifest])
def list_runs(version: Optional[str] = None):
    manifests = server.load_manifests()
    needs_version = [m for m in manifests if not m.version]
    if needs_version:
        conn = server.get_connection(read_only=False)
        db_versions = {r[0]: r[1] for r in conn.execute(
            "SELECT id, version FROM runs WHERE id = ANY(?)",
            [[m.runId for m in needs_version]],
        ).fetchall()}
        conn.close()
        for m in needs_version:
            if m.runId in db_versions and db_versions[m.runId]:
                m.version = db_versions[m.runId]
    if version:
        manifests = [m for m in manifests if m.version == version]
    manifests.sort(key=lambda m: str(m.timestamp), reverse=True)
    return manifests


@router.get("/api/v1/runs/{run_id}", response_model=RunManifest)
def get_run(run_id: str):
    for m in server.load_manifests():
        if m.runId == run_id:
            return m
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run '{run_id}' not found")


@router.get("/api/v1/runs/{run_id}/failures", response_model=List[ScenarioResult])
def get_run_failures(run_id: str):
    for m in server.load_manifests():
        if m.runId == run_id:
            return [s for s in m.scenarios if s.status in ("failed", "broken")]
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run '{run_id}' not found")


@router.get("/api/v1/runs/{run_id}/bug-status", response_model=List)
def get_bug_statuses(run_id: str):
    manifest_path = server.MANIFESTS_DIR / f"{run_id}.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    manifest = json.loads(manifest_path.read_text())
    results = []
    for s in manifest.get("scenarios", []):
        doors = s.get("doorsAbsNumber")
        result = {"scenarioId": s.get("id", ""), "doorsAbsNumber": doors, "isReported": False}
        if doors:
            bug = server.tracker.get(doors)
            if bug:
                result["jiraKey"] = bug.get("jiraKey")
                result["jiraUrl"] = server.jira_client.issue_url(bug["jiraKey"]) if server.jira_client.is_configured() else None
                result["status"] = bug.get("status")
                result["isReported"] = True
        results.append(result)
    return results


class RenameRequest(BaseModel):
    displayName: str


@router.patch("/api/v1/runs/{run_id}", response_model=dict, dependencies=[Depends(server.verify_token)])
def rename_run(run_id: str, req: RenameRequest, _: server.TokenData = Depends(server.verify_token)):
    manifest_path = server.MANIFESTS_DIR / f"{run_id}.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    aliases = server._load_aliases()
    aliases[run_id] = req.displayName
    server._save_aliases(aliases)
    return {"runId": run_id, "displayName": req.displayName}


@router.get("/api/scenario-history", dependencies=[Depends(server.verify_token)])
def list_scenario_history():
    conn = server.get_connection(read_only=True)
    try:
        server.init_schema(conn)
        return server.get_scenario_history(conn)
    finally:
        conn.close()


@router.get("/api/scenario-history/{doors_number}", dependencies=[Depends(server.verify_token)])
def get_scenario_history_item(doors_number: str):
    conn = server.get_connection(read_only=True)
    try:
        server.init_schema(conn)
        result = server.get_scenario_history(conn, doors_number)
        if not result:
            raise HTTPException(status_code=404, detail=f"DOORS number '{doors_number}' not found")
        return result
    finally:
        conn.close()


@router.get("/api/scenario-matrix", dependencies=[Depends(server.verify_token)])
def list_scenario_matrix(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    conn = server.get_connection(read_only=True)
    try:
        server.init_schema(conn)
        return server.get_scenario_matrix(conn, limit, offset)
    finally:
        conn.close()
