import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import httpx
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
from jira_client import JiraClient

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

MANIFESTS_DIR = Path(os.getenv("MANIFESTS_DIR", str(Path(__file__).parent.parent / "manifests")))
TEMPLATES_DIR = Path(__file__).parent / "templates"
RUN_ALIASES_FILE = Path(__file__).parent.parent / "run-aliases.json"

import threading
_aliases_lock = threading.Lock()

def _load_aliases() -> dict:
    if not RUN_ALIASES_FILE.exists():
        return {}
    with _aliases_lock:
        return json.loads(RUN_ALIASES_FILE.read_text())

def _save_aliases(data: dict) -> None:
    with _aliases_lock:
        RUN_ALIASES_FILE.write_text(json.dumps(data, indent=2))

def get_run_alias(run_id: str) -> str:
    return _load_aliases().get(run_id, run_id)

tracker = BugTracker(str(Path(__file__).parent.parent / "bug-tracker.json"))
jira_client = JiraClient()

app = FastAPI(title="Test Reports API", version="1.0.0")

jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
jinja_env.tests["contains"] = lambda value, item: item in value if value else False

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
def list_runs():
    manifests = load_manifests()
    manifests.sort(key=lambda m: str(m.timestamp), reverse=True)
    return manifests


@app.get("/api/v1/runs/{run_id}", response_model=RunManifest)
def get_run(run_id: str):
    manifests = load_manifests()
    for m in manifests:
        if m.runId == run_id:
            return m
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Run '{run_id}' not found",
    )


@app.get("/api/v1/runs/{run_id}/failures", response_model=List[ScenarioResult])
def get_run_failures(run_id: str):
    manifests = load_manifests()
    for m in manifests:
        if m.runId == run_id:
            return [s for s in m.scenarios if s.status == "failed"]
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Run '{run_id}' not found",
    )



@app.get("/reports/{run_id}/scenario/{scenario_id}")
def scenario_detail(run_id: str, scenario_id: str):
    manifest_path = MANIFESTS_DIR / f"{run_id}.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    manifest = json.loads(manifest_path.read_text())
    scenario = next((s for s in manifest.get("scenarios", []) if s.get("id") == scenario_id), None)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    template = jinja_env.get_template("scenario-detail.html")
    return HTMLResponse(content=template.render(run_id=run_id, scenario=scenario, manifest=manifest))
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

    template = jinja_env.get_template("triage.html")
    html = template.render(
        run_id=run_id,
        manifest=manifest.model_dump(),
        failures=[s.model_dump() for s in failures],
        jira_base_url=os.getenv("JIRA_BASE_URL", ""),
    )
    return HTMLResponse(content=html)


class JiraResponse(BaseModel):
    jiraKey: str
    jiraUrl: Optional[str] = None


@app.post("/api/v1/runs/{run_id}/scenarios/{scenario_id}/jira", response_model=JiraResponse, status_code=201)
def create_jira_bug(run_id: str, scenario_id: str):
    manifests = load_manifests()
    manifest = next((m for m in manifests if m.runId == run_id), None)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    scenario = next((s for s in manifest.scenarios if s.id == scenario_id), None)
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")

    if not jira_client.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Jira integration not configured. Set JIRA_BASE_URL, JIRA_PAT, JIRA_PROJECT.",
        )

    summary = f"Automated test failed: {scenario.name}"
    step_lines = "\n".join(
        f"  [FAIL] {s.name}" if s.status == "failed" else f"  [pass] {s.name}"
        for s in scenario.steps
    )
    description = (
        f"h2. Automated Test Failure\n\n"
        f"*Run ID:* {run_id}\n"
        f"*Scenario:* {scenario.name}\n"
        f"*Duration:* {scenario.duration}\n\n"
        f"h3. Steps\n{{noformat}}\n{step_lines}\n{{noformat}}"
    )

    try:
        key = jira_client.create_issue(summary, description)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Jira API error {exc.response.status_code}: {exc.response.text[:300]}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Jira error: {str(exc)}",
        )

    return JiraResponse(jiraKey=key, jiraUrl=jira_client.issue_url(key))


class BugCreateRequest(BaseModel):
    scenarioName: str
    runId: str


class BugCreateResponse(BaseModel):
    jiraKey: str
    doorsNumber: str


@app.get("/api/v1/bugs")
def list_bugs():
    return tracker.get_all()


@app.get("/api/v1/bugs/{doors_number}")
def get_bug(doors_number: str):
    mapping = tracker.get(doors_number)
    if mapping is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No mapping found for DOORS number: {doors_number}",
        )
    return mapping


@app.post(
    "/api/v1/bugs/{doors_number}/create",
    response_model=BugCreateResponse,
    status_code=201,
    dependencies=[Depends(verify_token)],
)
def create_bug(doors_number: str, req: BugCreateRequest, _: TokenData = Depends(verify_token)):
    existing = tracker.get(doors_number)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=existing,
        )
    jira_key = f"PROJ-{abs(hash(doors_number)) % 9000 + 1000}"
    tracker.register(doors_number, jira_key, req.scenarioName, req.runId)
    return BugCreateResponse(jiraKey=jira_key, doorsNumber=doors_number)


class RenameRequest(BaseModel):
    displayName: str

@app.patch("/api/v1/runs/{run_id}", response_model=dict, dependencies=[Depends(verify_token)])
def rename_run(run_id: str, req: RenameRequest, _: TokenData = Depends(verify_token)):
    manifest_path = MANIFESTS_DIR / f"{run_id}.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    aliases = _load_aliases()
    aliases[run_id] = req.displayName
    _save_aliases(aliases)
    return {"runId": run_id, "displayName": req.displayName}

class BugStatusResult(BaseModel):
    scenarioId: str
    doorsAbsNumber: Optional[str] = None
    jiraKey: Optional[str] = None
    jiraUrl: Optional[str] = None
    status: Optional[str] = None
    isReported: bool = False

@app.get("/api/v1/runs/{run_id}/bug-status", response_model=List[BugStatusResult])
def get_bug_statuses(run_id: str):
    manifest_path = MANIFESTS_DIR / f"{run_id}.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    manifest = json.loads(manifest_path.read_text())
    results = []
    for s in manifest.get("scenarios", []):
        doors = s.get("doorsAbsNumber")
        result = BugStatusResult(
            scenarioId=s.get("id", ""),
            doorsAbsNumber=doors,
            isReported=False,
        )
        if doors:
            bug = tracker.get(doors)
            if bug:
                result.jiraKey = bug.get("jiraKey")
                result.jiraUrl = jira_client.issue_url(bug["jiraKey"]) if jira_client.is_configured() else None
                result.status = bug.get("status")
                result.isReported = True
        results.append(result)
    return results

@app.get("/reports/{run_id}", response_class=HTMLResponse)
def run_detail(run_id: str, request: Request):
    manifests = load_manifests()
    manifest = None
    for m in manifests:
        if m.runId == run_id:
            manifest = m
            break
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    display_name = get_run_alias(run_id)

    template = jinja_env.get_template("run-detail.html")
    html = template.render(
        run_id=run_id,
        display_name=display_name,
        manifest=manifest.model_dump(),
        scenarios=manifest.scenarios,
        jira_base_url=os.getenv("JIRA_BASE_URL", ""),
    )
    return HTMLResponse(content=html)

MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/reports", StaticFiles(directory=str(MANIFESTS_DIR)), name="reports")
app.mount("/static", StaticFiles(directory="static"), name="static")
