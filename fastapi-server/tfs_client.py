import base64
import os
from typing import Any, NoReturn, Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel
import jwt


class TFSClient:
    def __init__(self):
        self.org_url = os.getenv("AZURE_ORG_URL", "").rstrip("/")
        self.project = os.getenv("AZURE_PROJECT", "")
        pat = os.getenv("AZURE_PAT", "")
        auth_str = base64.b64encode(bytes(":" + pat, "ascii")).decode("ascii")
        self.headers = {
            "Authorization": f"Basic {auth_str}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def is_configured(self) -> bool:
        return bool(self.org_url and self.project and self.headers.get("Authorization"))

    def _pipeline_url(self, pipeline_id: int, run_id: Optional[int] = None) -> str:
        project = quote(self.project.strip("/"), safe="")
        path = f"{self.org_url}/{project}/_apis/pipelines/{pipeline_id}/runs"
        if run_id is not None:
            path = f"{path}/{run_id}"
        return f"{path}?api-version=7.1"

    async def trigger_pipeline(self, pipeline_id: int, variables: Optional[dict[str, Any]] = None):
        url = self._pipeline_url(pipeline_id)
        payload: dict[str, Any] = {
            "resources": {"repositories": {"self": {"refName": "refs/heads/main"}}}
        }
        if variables:
            payload["variables"] = {k: {"value": str(v)} for k, v in variables.items()}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=self.headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    async def get_run_status(self, pipeline_id: int, run_id: int):
        url = self._pipeline_url(pipeline_id, run_id)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=self.headers)
            resp.raise_for_status()
            return resp.json()


class TriggerRequest(BaseModel):
    pipeline_id: int
    variables: Optional[dict[str, Any]] = None


router = APIRouter(prefix="/api/tfs")
tfs = TFSClient()

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
security = HTTPBearer()


def verify_token(credentials: HTTPBearer = Depends(security)) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


def _raise_tfs_error(exc: httpx.HTTPStatusError) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Azure DevOps API error {exc.response.status_code}: {exc.response.text[:300]}",
    )


@router.post("/trigger", dependencies=[Depends(verify_token)])
async def trigger(request: TriggerRequest):
    try:
        result = await tfs.trigger_pipeline(request.pipeline_id, request.variables)
    except httpx.HTTPStatusError as exc:
        _raise_tfs_error(exc)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Azure DevOps connection error: {str(exc)}",
        )
    return {"run_id": result.get("id"), "status": "queued"}


@router.post("/webhook", dependencies=[Depends(verify_token)])
async def webhook(payload: dict[str, Any]):
    return {"received": True}


@router.get("/status/{pipeline_id}/{run_id}", dependencies=[Depends(verify_token)])
async def get_status(pipeline_id: int, run_id: int):
    try:
        return await tfs.get_run_status(pipeline_id, run_id)
    except httpx.HTTPStatusError as exc:
        _raise_tfs_error(exc)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Azure DevOps connection error: {str(exc)}",
        )
