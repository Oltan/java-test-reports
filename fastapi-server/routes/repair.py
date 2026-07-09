"""LLM repair routes (rulebook L2): propose a fix for a failed run, apply it,
optionally re-run the same tags. Shared state via ``server.X`` like every other
route module (monkeypatch surface preserved, no import cycle)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

import server
from services.repair import (
    apply_proposal,
    build_messages,
    collect_context,
    parse_proposal,
    validate_target,
)

router = APIRouter()


class ProposeRequest(BaseModel):
    scenario_uid: Optional[str] = None


class ApplyRequest(BaseModel):
    file: str
    new_content: str
    explanation: str = ""
    rerun: bool = True


@router.post("/api/repair/{run_id}/propose", dependencies=[Depends(server.verify_token)])
def propose_repair(run_id: str, req: ProposeRequest | None = None):
    if not server.llm_client.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM repair not configured. Set OPENAI_API_KEY (and optionally OPENAI_BASE_URL/OPENAI_MODEL).",
        )
    scenario_uid = req.scenario_uid if req else None
    conn = server.get_connection(read_only=False)
    try:
        server.init_schema(conn)
        context = collect_context(conn, run_id, server.MANIFESTS_DIR, scenario_uid)
    finally:
        conn.close()
    if not context["target"]:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' has no matching FAILED/BROKEN scenario")

    try:
        raw = server.llm_client.chat(build_messages(context))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"LLM error: {exc}")
    try:
        proposal = parse_proposal(raw)
        validate_target(proposal["file"])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return {
        "run_id": run_id,
        "scenario": context["target"]["name"],
        "scenario_uid": context["target"]["scenario_uid"],
        "proposal": proposal,
    }


@router.post("/api/repair/{run_id}/apply", dependencies=[Depends(server.verify_token)])
async def apply_repair(run_id: str, req: ApplyRequest):
    try:
        applied = apply_proposal({"file": req.file, "new_content": req.new_content})
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    result: dict = {"run_id": run_id, "applied": applied, "explanation": req.explanation}

    if req.rerun:
        conn = server.get_connection(read_only=False)
        try:
            server.init_schema(conn)
            row = conn.execute(
                "SELECT tags, browser, environment FROM worker_runs WHERE run_id = ?", [run_id]
            ).fetchone()
        finally:
            conn.close()
        if not row:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found for re-run")
        options = server.TestRunOptions(
            tags=row[0], browser=row[1] or "chrome", environment=row[2] or "staging", force=True
        )
        from routes.tests import start_tests

        result["rerun"] = await start_tests(options, None)
    return result
