"""HTML page routes (dashboard, admin, run-detail, scenario-detail, triage,
artifact serving), split out of server.py.

Route order matters: the catch-all /reports/{artifact_path:path} stays LAST so
it doesn't shadow /reports/{run_id}[/...]. Shared state referenced as server.X.
"""
import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse

import server

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    manifests = server.load_manifests()
    total_runs = len(manifests)
    latest_run = None
    if manifests:
        sorted_manifests = sorted(manifests, key=lambda m: str(m.timestamp), reverse=True)
        latest_run = sorted_manifests[0].model_dump()
    template = server.jinja_env.get_template("dashboard.html")
    html = template.render(total_runs=total_runs, latest_run=latest_run)
    return HTMLResponse(content=html)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    template = server.jinja_env.get_template("dashboard.html")
    return HTMLResponse(content=template.render())


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    template = server.jinja_env.get_template("admin.html")
    return HTMLResponse(content=template.render())


@router.get("/reports/merge", response_class=HTMLResponse)
async def report_merge_page(request: Request, _: server.TokenData = Depends(server.verify_token_page)):
    template = server.jinja_env.get_template("report-merge.html")
    return HTMLResponse(content=template.render())


@router.get("/reports/{run_id}", response_class=HTMLResponse)
def run_detail(run_id: str, request: Request, _: server.TokenData = Depends(server.verify_token_page)):
    # Check public visibility first (no auth required)
    conn = server.get_connection(read_only=False)
    try:
        server.init_schema(conn)
        run_row = conn.execute("SELECT id, visibility FROM runs WHERE id = ?", [run_id]).fetchone()
        if run_row and run_row[1] == "public":
            scenarios = conn.execute(
                "SELECT name_at_run, status, duration_seconds FROM scenario_results WHERE run_id = ?",
                [run_id],
            ).fetchall()
            template = server.jinja_env.get_template("public_report.html")
            return HTMLResponse(content=template.render(run_id=run_id, scenarios=scenarios))
    except Exception:
        pass
    finally:
        conn.close()

    manifest = next((m for m in server.load_manifests() if m.runId == run_id), None)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    template = server.jinja_env.get_template("run-detail.html")
    html = template.render(
        run_id=run_id,
        display_name=server.get_run_alias(run_id),
        manifest=manifest.model_dump(),
        scenarios=manifest.scenarios,
        jira_base_url=os.getenv("JIRA_BASE_URL", ""),
    )
    return HTMLResponse(content=html)


@router.get("/reports/{run_id}/scenario/{scenario_id}")
def scenario_detail(run_id: str, scenario_id: str, _: server.TokenData = Depends(server.verify_token_page)):
    manifest_path = server.MANIFESTS_DIR / f"{run_id}.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    manifest = json.loads(manifest_path.read_text())
    scenario = next((s for s in manifest.get("scenarios", []) if s.get("id") == scenario_id), None)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    template = server.jinja_env.get_template("scenario-detail.html")
    return HTMLResponse(content=template.render(run_id=run_id, scenario=scenario, manifest=manifest))


@router.get("/reports/{run_id}/triage")
def triage_page(run_id: str, request: Request, _: server.TokenData = Depends(server.verify_token_page)):
    manifest = next((m for m in server.load_manifests() if m.runId == run_id), None)
    if manifest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run '{run_id}' not found")
    failures = [s for s in manifest.scenarios if s.status in ("failed", "broken")]

    template = server.jinja_env.get_template("triage.html")
    html = template.render(
        run_id=run_id,
        manifest=manifest.model_dump(),
        failures=[s.model_dump() for s in failures],
        jira_base_url=os.getenv("JIRA_BASE_URL", ""),
    )
    return HTMLResponse(content=html)


@router.get("/reports/{artifact_path:path}")
def protected_report_artifact(artifact_path: str, _: server.TokenData = Depends(server.verify_token_page)):
    """Serve report attachments only to authenticated engineer sessions, resolved
    under MANIFESTS_DIR to prevent path traversal."""
    candidate = (server.MANIFESTS_DIR / artifact_path).resolve()
    reports_root = server.MANIFESTS_DIR.resolve()
    try:
        candidate.relative_to(reports_root)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    if not candidate.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    return FileResponse(candidate)
