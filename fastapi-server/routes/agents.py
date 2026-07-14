"""Agent orchestration endpoints (OpenCode sidecar + Jira/repair advice)."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

import server
from services.opencode_agent import build_failure_advice_prompt
from services.repair import collect_context

router = APIRouter()


class AgentAdviceRequest(BaseModel):
    scenario_uid: Optional[str] = None
    intent: Literal["repair", "jira", "both"] = "both"
    agent: str = Field(default="repair", pattern=r"^[A-Za-z0-9_.-]+$")


@router.get("/api/agent/opencode/status", dependencies=[Depends(server.verify_token)])
def opencode_status():
    return server.opencode_agent.status()


@router.post("/api/agent/runs/{run_id}/advise", dependencies=[Depends(server.verify_token)])
def opencode_advise(run_id: str, req: AgentAdviceRequest | None = None):
    request = req or AgentAdviceRequest()
    if not server.opencode_agent.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenCode not configured. Install opencode or set OPENCODE_CMD.",
        )

    conn = server.get_connection(read_only=False)
    try:
        server.init_schema(conn)
        context = collect_context(conn, run_id, server.MANIFESTS_DIR, request.scenario_uid)
    finally:
        conn.close()
    if not context["target"]:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' has no matching FAILED/BROKEN scenario")

    prompt = build_failure_advice_prompt(context, intent=request.intent)
    try:
        result = server.opencode_agent.run(prompt, agent=request.agent)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"OpenCode error: {exc}")

    return {
        "run_id": run_id,
        "scenario_uid": context["target"]["scenario_uid"],
        "scenario": context["target"]["name"],
        "intent": request.intent,
        "exit_code": result.exit_code,
        "command": result.command[:6] + ["<prompt>"] if result.command else [],
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
        "advice": result.parsed,
    }
