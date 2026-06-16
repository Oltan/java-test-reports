"""Auth, pipeline-control and WebSocket routes, split out of server.py.

Shared state/helpers referenced as server.X to preserve the test monkeypatch
surface and avoid an import cycle.
"""
from uuid import uuid4

import jwt
from fastapi import (
    APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response,
    WebSocket, WebSocketDisconnect, status,
)

import server

router = APIRouter()


@router.post("/api/pipeline/run", dependencies=[Depends(server.verify_token)])
async def trigger_pipeline(background_tasks: BackgroundTasks, run_id: str | None = None):
    job_id = run_id or f"auto-{uuid4()}"
    background_tasks.add_task(server.execute_pipeline, job_id)
    return {"status": "started", "run_id": job_id, "job_id": job_id}


@router.get("/api/pipeline/status/{run_id}", dependencies=[Depends(server.verify_token)])
async def pipeline_status(run_id: str):
    conn = server.get_connection(read_only=False)
    try:
        server.init_schema(conn)
        rows = conn.execute(
            """
            SELECT stage, status, error_message
            FROM pipeline_status
            WHERE run_id=?
            ORDER BY stage
            """,
            [run_id],
        ).fetchall()
    finally:
        conn.close()
    return {
        "run_id": run_id,
        "stages": [{"stage": r[0], "status": r[1], "error": r[2]} for r in rows],
    }


@router.post("/api/v1/auth/login", response_model=server.LoginResponse)
def login(req: server.LoginRequest, response: Response):
    if req.username != server.ADMIN_USERNAME or req.password != server.ADMIN_PASSWORD:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = server.create_token(req.username)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=False,
        max_age=server.JWT_EXPIRATION_HOURS * 3600,
        samesite="lax",
        path="/",
    )
    return server.LoginResponse(token=token)


def _auth_ws(token: str) -> bool:
    try:
        payload = jwt.decode(token, server.JWT_SECRET, algorithms=[server.JWT_ALGORITHM])
        return payload.get("sub") is not None
    except jwt.InvalidTokenError:
        return False


@router.websocket("/ws/test-status/live")
async def ws_test_status(websocket: WebSocket, token: str = Query(...)):
    if not _auth_ws(token):
        await websocket.close(code=4001)
        return
    await server.ws_manager.connect("live", websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        server.ws_manager.disconnect("live", websocket)


@router.websocket("/ws/test-status/{run_id}")
async def ws_test_run(websocket: WebSocket, run_id: str, token: str = Query(...)):
    if not _auth_ws(token):
        await websocket.close(code=4001)
        return
    await server.ws_manager.connect(run_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        server.ws_manager.disconnect(run_id, websocket)
