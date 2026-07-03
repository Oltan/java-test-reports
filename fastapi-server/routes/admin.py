"""Admin (sync/delete), user management, service tokens, and read-only
dashboard-metrics routes, split out of server.py. Shared helpers referenced
as server.X."""
import os
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import server

router = APIRouter()


@router.post("/api/admin/sync-runs", dependencies=[Depends(server.verify_token)])
def admin_sync_runs():
    """Backfill manifests ↔ DuckDB so version filters work across all historical runs."""
    return server.sync_runs()


@router.delete("/api/admin/runs/{run_id}", dependencies=[Depends(server.verify_token)])
def delete_run(run_id: str):
    with server.get_connection(read_only=False) as conn:
        server.init_schema(conn)
        conn.execute("DELETE FROM scenario_results WHERE run_id = ?", [run_id])
        conn.execute("DELETE FROM pipeline_status WHERE run_id = ?", [run_id])
        conn.execute("DELETE FROM runs WHERE id = ?", [run_id])
        conn.commit()
    manifest_path = server.MANIFESTS_DIR / f"{run_id}.json"
    if manifest_path.exists():
        manifest_path.unlink()
    return {"deleted": run_id}


@router.delete("/api/admin/runs", dependencies=[Depends(server.verify_token)])
def delete_all_runs():
    with server.get_connection(read_only=False) as conn:
        server.init_schema(conn)
        conn.execute("DELETE FROM scenario_results")
        conn.execute("DELETE FROM pipeline_status")
        conn.execute("DELETE FROM runs")
        conn.commit()
    if server.MANIFESTS_DIR.exists():
        for f in server.MANIFESTS_DIR.glob("*.json"):
            f.unlink()
    return {"deleted": "all"}


@router.get("/api/versions")
async def get_versions():
    conn = server.get_connection(read_only=False)
    try:
        server.init_schema(conn)
        rows = conn.execute(
            "SELECT DISTINCT version FROM runs WHERE version IS NOT NULL ORDER BY version DESC"
        ).fetchall()
        return {"versions": [r[0] for r in rows]}
    finally:
        conn.close()


@router.get("/api/dashboard/metrics")
async def dashboard_metrics(
    version: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    conn = server.get_connection(read_only=True)
    try:
        query = (
            "SELECT COUNT(*) as runs, "
            "COALESCE(SUM(passed),0) as passed, "
            "COALESCE(SUM(failed),0) as failed, "
            "COALESCE(SUM(skipped),0) as skipped, "
            "COALESCE(AVG(CAST(total_scenarios AS DOUBLE)),0) as avg_scenarios "
            "FROM runs WHERE 1=1"
        )
        params: list = []
        if version:
            query += " AND version = ?"
            params.append(version)
        if start:
            query += " AND started_at >= ?"
            params.append(start)
        if end:
            query += " AND started_at <= ?"
            params.append(end)
        row = conn.execute(query, params).fetchone()
        if row is None:
            return {"success_rate": 0, "total_runs": 0, "passed": 0, "failed": 0, "skipped": 0, "avg_duration": 0, "flaky_count": 0, "version_breakdown": []}
        row = cast(tuple, row)

        # Flaky count: scenarios that have both PASSED and FAILED across runs
        flaky_query = (
            "SELECT COUNT(DISTINCT sr.scenario_uid) FROM scenario_results sr "
            "JOIN runs r ON sr.run_id = r.id WHERE 1=1"
        )
        flaky_params: list = []
        if version:
            flaky_query += " AND r.version = ?"
            flaky_params.append(version)
        if start:
            flaky_query += " AND r.started_at >= ?"
            flaky_params.append(start)
        if end:
            flaky_query += " AND r.started_at <= ?"
            flaky_params.append(end)
        flaky_query += (
            " AND sr.scenario_uid IN ("
            "  SELECT scenario_uid FROM scenario_results "
            "  WHERE status IN ('PASSED','FAILED') "
            "  GROUP BY scenario_uid HAVING COUNT(DISTINCT status) > 1"
            ")"
        )
        flaky_result = conn.execute(flaky_query, flaky_params).fetchone()
        flaky_count = flaky_result[0] if flaky_result else 0

        total = row[1] + row[2] + row[3]
        success_rate = round((row[1] / total * 100), 1) if total > 0 else 0

        # Version breakdown for bar chart
        version_query = (
            "SELECT version, SUM(passed) as passed, SUM(failed) as failed, "
            "SUM(skipped) as skipped FROM runs WHERE version IS NOT NULL"
        )
        v_params: list = []
        if version:
            version_query += " AND version = ?"
            v_params.append(version)
        if start:
            version_query += " AND started_at >= ?"
            v_params.append(start)
        if end:
            version_query += " AND started_at <= ?"
            v_params.append(end)
        version_query += " GROUP BY version ORDER BY version DESC"
        version_rows = conn.execute(version_query, v_params).fetchall()
        version_breakdown = [
            {"version": r[0], "passed": r[1], "failed": r[2], "skipped": r[3]}
            for r in version_rows
        ]

        return {
            "success_rate": success_rate,
            "total_runs": row[0],
            "passed": row[1],
            "failed": row[2],
            "skipped": row[3],
            "avg_duration": round(row[4], 1),
            "flaky_count": flaky_count,
            "version_breakdown": version_breakdown,
        }
    finally:
        conn.close()


# ── User management (admin only) ─────────────────────────────────────────────

class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: Literal["admin", "runner"]


class UserCreateResponse(BaseModel):
    username: str
    role: str


@router.get("/api/admin/users", dependencies=[Depends(server.require_role("admin"))])
def list_admin_users():
    conn = server.get_connection(read_only=False)
    try:
        server.init_schema(conn)
        return {"users": server.list_users(conn)}
    finally:
        conn.close()


@router.post(
    "/api/admin/users",
    response_model=UserCreateResponse,
    status_code=201,
    dependencies=[Depends(server.require_role("admin"))],
)
def create_admin_user(req: UserCreateRequest):
    if not req.username.strip() or not req.password:
        raise HTTPException(status_code=422, detail="username and password are required")
    conn = server.get_connection(read_only=False)
    try:
        server.init_schema(conn)
        if server.get_user(conn, req.username) is not None:
            raise HTTPException(status_code=409, detail=f"User '{req.username}' already exists")
        server.create_user(conn, req.username, req.password, role=req.role)
        conn.commit()
        return UserCreateResponse(username=req.username, role=req.role)
    finally:
        conn.close()


@router.delete("/api/admin/users/{username}", dependencies=[Depends(server.require_role("admin"))])
def delete_admin_user(username: str, token: server.TokenData = Depends(server.verify_token)):
    if username == token.username:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    conn = server.get_connection(read_only=False)
    try:
        server.init_schema(conn)
        if server.get_user(conn, username) is None:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        server.delete_user(conn, username)
        conn.commit()
        return {"status": "deleted"}
    finally:
        conn.close()


# ── Service tokens (admin only, for AI-agent / automation clients) ──────────

class ServiceTokenRequest(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,31}$")
    days: Optional[int] = Field(default=None, ge=1, le=3650)


class ServiceTokenResponse(BaseModel):
    token: str
    name: str
    sub: str
    role: str
    expires_at: str


@router.post(
    "/api/admin/service-tokens",
    response_model=ServiceTokenResponse,
    dependencies=[Depends(server.require_role("admin"))],
)
def create_service_token_route(req: ServiceTokenRequest):
    # Read the env default at call time (rather than baking it into the Pydantic
    # field) so SERVICE_TOKEN_DAYS can change without a process restart mattering.
    days = req.days if req.days is not None else int(os.getenv("SERVICE_TOKEN_DAYS", "365"))
    token = server.create_service_token(req.name, days)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    return ServiceTokenResponse(
        token=token,
        name=req.name,
        sub=f"svc:{req.name}",
        role="agent",
        expires_at=expires_at,
    )
