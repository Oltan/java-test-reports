"""Run-listing, run-detail, rename and scenario-history/matrix routes.

Split out of server.py; shared state/helpers referenced as server.X to keep the
test monkeypatch surface (server.get_connection, …) intact.
"""
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

import server
from models import RunManifest, ScenarioResult, StepResult

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

    # Fallback for runs that never produced a manifest file — e.g. runs started
    # by the in-app runner (results are written straight to DuckDB, no manifest).
    # Any DB error here degrades to the same 404 as "unknown run" rather than a
    # 500, since this route is public and manifest-first.
    try:
        return _get_run_failures_from_duckdb(run_id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        )


def _get_run_failures_from_duckdb(run_id: str) -> List[ScenarioResult]:
    # read_only=False: init_schema issues CREATE TABLE IF NOT EXISTS, which
    # DuckDB rejects on read-only connections (matches the other endpoints).
    conn = server.get_connection(read_only=False)
    try:
        server.init_schema(conn)
        run_known = conn.execute("SELECT 1 FROM runs WHERE id = ?", [run_id]).fetchone()
        if not run_known:
            run_known = conn.execute(
                "SELECT 1 FROM scenario_results WHERE run_id = ? LIMIT 1", [run_id]
            ).fetchone()
        if not run_known:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run '{run_id}' not found",
            )

        rows = conn.execute(
            """
            SELECT sr.scenario_uid, sr.name_at_run, sr.status, sr.duration_seconds, sr.error_message,
                   sr.feature_file_at_run, sr.doors_number_at_run, sr.retry_attempt
            FROM scenario_results sr WHERE sr.run_id = ? AND sr.status IN ('FAILED','BROKEN')
            ORDER BY sr.retry_attempt ASC
            """,
            [run_id],
        ).fetchall()
    finally:
        conn.close()

    # Keep only the last (highest retry_attempt) row per scenario_uid — rows are
    # ordered ascending by retry_attempt above, so a later row for the same uid
    # simply overwrites the earlier one here.
    last_by_uid: dict[str, tuple] = {}
    for i, row in enumerate(rows):
        uid = row[0] or f"{run_id}-{i}"
        last_by_uid[uid] = row

    results: List[ScenarioResult] = []
    for uid, (_uid, name, db_status, duration, error_message, _feature_file, doors_number, _retry) in last_by_uid.items():
        steps: List[StepResult] = []
        if error_message:
            steps.append(StepResult(name="error", status="failed", errorMessage=error_message))
        results.append(
            ScenarioResult(
                id=uid,
                name=name,
                status=db_status.lower(),
                duration=str(duration or 0),
                doorsAbsNumber=doors_number,
                tags=[],
                steps=steps,
                attachments=[],
                attempts=[],
                dependencies=[],
            )
        )
    return results


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
