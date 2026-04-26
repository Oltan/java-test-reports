import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

from models import RunManifest, ScenarioResult
from bug_tracker import BugTracker

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")

tracker = BugTracker(str(Path(__file__).parent.parent / "bug-tracker.json"))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

MANIFESTS_DIR = Path(os.getenv("MANIFESTS_DIR", str(Path(__file__).parent.parent / "manifests")))
TEMPLATES_DIR = Path(__file__).parent / "templates"

app = FastAPI(title="Test Reports API", version="1.0.0")

jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    manifests = load_manifests()
    total_runs = len(manifests)
    latest_run = None
    if manifests:
        sorted_manifests = sorted(manifests, key=lambda m: str(m.timestamp), reverse=True)
        latest_run = sorted_manifests[0].model_dump()
    template = jinja_env.get_template("dashboard.html")
    html = template.render(
        total_runs=total_runs,
        latest_run=latest_run,
    )
    return HTMLResponse(content=html)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str


class TokenData(BaseModel):
    username: str


def create_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> TokenData:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject",
            )
        return TokenData(username=username)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


def load_manifests() -> List[RunManifest]:
    if not MANIFESTS_DIR.exists():
        return []
    manifests = []
    for f in sorted(MANIFESTS_DIR.glob("*.json")):
        with open(f) as fh:
            data = json.load(fh)
        manifests.append(RunManifest.model_validate(data))
    return manifests


@app.post("/api/v1/auth/login", response_model=LoginResponse)
def login(req: LoginRequest):
    if req.username != ADMIN_USERNAME or req.password != ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token = create_token(req.username)
    return LoginResponse(token=token)


@app.get("/api/v1/runs", response_model=List[RunManifest])
def list_runs(_: TokenData = Depends(verify_token)):
    manifests = load_manifests()
    manifests.sort(key=lambda m: str(m.timestamp), reverse=True)
    return manifests


@app.get("/api/v1/runs/{run_id}", response_model=RunManifest)
def get_run(run_id: str, _: TokenData = Depends(verify_token)):
    manifests = load_manifests()
    for m in manifests:
        if m.runId == run_id:
            return m
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Run '{run_id}' not found",
    )


@app.get("/api/v1/runs/{run_id}/failures", response_model=List[ScenarioResult])
def get_run_failures(run_id: str, _: TokenData = Depends(verify_token)):
    manifests = load_manifests()
    for m in manifests:
        if m.runId == run_id:
            return [s for s in m.scenarios if s.status == "failed"]
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Run '{run_id}' not found",
    )


@app.get("/reports/{run_id}/triage")
def triage_page(run_id: str, request: Request):
    manifests = load_manifests()
    manifest = None
    for m in manifests:
        if m.runId == run_id:
            manifest = m
            break
    if manifest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        )
    failures = [s for s in manifest.scenarios if s.status == "failed"]

    # Extract JWT token from Authorization header for client-side API calls
    token = ""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]

    template = jinja_env.get_template("triage.html")
    html = template.render(
        run_id=run_id,
        manifest=manifest.model_dump(),
        failures=[s.model_dump() for s in failures],
        token=token,
    )
    return HTMLResponse(content=html)


class JiraResponse(BaseModel):
    jiraKey: str


@app.post("/api/v1/runs/{run_id}/scenarios/{scenario_id}/jira", response_model=JiraResponse, status_code=201)
def create_jira_bug(run_id: str, scenario_id: str):
    manifests = load_manifests()
    manifest = None
    for m in manifests:
        if m.runId == run_id:
            manifest = m
            break
    if manifest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        )
    scenario = None
    for s in manifest.scenarios:
        if s.id == scenario_id:
            scenario = s
            break
    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario '{scenario_id}' not found",
        )
    # Mock Jira creation — replace with real Jira service call later
    return JiraResponse(jiraKey="PROJ-123")


class BugCreateRequest(BaseModel):
    scenarioName: str
    runId: str


class BugCreateResponse(BaseModel):
    jiraKey: str
    doorsNumber: str


@app.get("/api/v1/bugs", dependencies=[Depends(verify_token)])
def list_bugs(_: TokenData = Depends(verify_token)):
    return tracker.get_all()


@app.get("/api/v1/bugs/{doors_number}", dependencies=[Depends(verify_token)])
def get_bug(doors_number: str, _: TokenData = Depends(verify_token)):
    mapping = tracker.get(doors_number)
    if mapping is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No mapping found for DOORS number: {doors_number}",
        )
    return mapping


@app.post("/api/v1/bugs/{doors_number}/create", response_model=BugCreateResponse, status_code=201, dependencies=[Depends(verify_token)])
def create_bug(doors_number: str, req: BugCreateRequest, _: TokenData = Depends(verify_token)):
    existing = tracker.get(doors_number)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=existing,
        )
    # Mock Jira key: PROJ-{hash(doors_number) % 9000 + 1000}
    jira_key = f"PROJ-{abs(hash(doors_number)) % 9000 + 1000}"
    tracker.register(doors_number, jira_key, req.scenarioName, req.runId)
    return BugCreateResponse(jiraKey=jira_key, doorsNumber=doors_number)


app.mount("/reports", StaticFiles(directory=str(MANIFESTS_DIR)), name="reports")
app.mount("/static", StaticFiles(directory="static"), name="static")