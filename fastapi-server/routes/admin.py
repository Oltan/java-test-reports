"""Admin (sync/delete) and read-only dashboard-metrics routes, split out of
server.py. Shared helpers referenced as server.X."""
from typing import Optional, cast

from fastapi import APIRouter, Depends

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
