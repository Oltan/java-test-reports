import json
import os
import shutil
import subprocess
import threading
import asyncio
from datetime import datetime, timedelta, timezone
from importlib import import_module
from pathlib import Path
from typing import List, Optional, cast
from uuid import uuid4

import httpx
import jwt
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

from models import RunManifest, ScenarioResult, TestRunOptions
from bug_tracker import BugTracker
from db import get_connection, init_schema
from jira_client import JiraClient
from pipeline import execute_pipeline
from doors_service import run_doors_dxl, is_doors_available  # type: ignore[reportMissingImports]
from email_service import send_email  # type: ignore[reportMissingImports]
from websocket_handler import manager as ws_manager, stream_test_output  # type: ignore[reportMissingImports]

load_dotenv()

tfs_router = import_module("tfs_client").router

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

MANIFESTS_DIR = Path(os.getenv("MANIFESTS_DIR", str(Path(__file__).parent.parent / "manifests")))
TEMPLATES_DIR = Path(__file__).parent / "templates"
RUN_ALIASES_FILE = Path(__file__).parent.parent / "run-aliases.json"
PROJECT_ROOT = Path(__file__).parent.parent

_aliases_lock = threading.Lock()

running_tests: dict[str, object] = {}
test_tasks: set[asyncio.Task] = set()
tests_lock = threading.Lock()

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
app.include_router(tfs_router)

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


@app.post("/api/pipeline/run")
async def trigger_pipeline(background_tasks: BackgroundTasks, run_id: Optional[str] = None):
    job_id = run_id or f"auto-{uuid4()}"
    background_tasks.add_task(execute_pipeline, job_id)
    return {"status": "started", "run_id": job_id, "job_id": job_id}


def _maven_executable() -> str:
    configured = os.getenv("MAVEN_CMD")
    if configured:
        return configured
    bundled = Path("/home/ol_ta/tools/apache-maven-3.9.9/bin/mvn")
    if bundled.exists():
        return str(bundled)
    return shutil.which("mvn") or "mvn"


def _test_command(options: TestRunOptions) -> list[str]:
    cmd = [
        _maven_executable(),
        "-pl",
        "test-core",
        "test",
        f"-Dcucumber.filter.tags={options.tags}",
    ]
    if options.retry_count:
        cmd.append(f"-Dretry.count={options.retry_count}")
    return cmd


def _test_env() -> dict[str, str]:
    env = os.environ.copy()
    env["DISPLAY"] = env.get("DISPLAY", ":0")
    maven_parent = Path(_maven_executable()).parent
    if str(maven_parent) != ".":
        env["PATH"] = f"{maven_parent}{os.pathsep}{env.get('PATH', '')}"
    return env


def _wait_for_test_run(run_id: str, proc: subprocess.Popen) -> None:
    try:
        proc.wait()
    finally:
        with tests_lock:
            running_tests.pop(run_id, None)


def _launch_test_run(run_id: str, options: TestRunOptions) -> subprocess.Popen:
    try:
        proc = subprocess.Popen(_test_command(options), cwd=str(PROJECT_ROOT), env=_test_env())
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start test run: {exc}") from exc
    with tests_lock:
        running_tests[run_id] = proc
    return proc


@app.post("/api/tests/start")
async def start_tests(options: TestRunOptions, background_tasks: BackgroundTasks):
    """Start tests with validated options. Invalid options are rejected by Pydantic."""
    del background_tasks
    run_ids = []
    for _ in range(options.parallel):
        run_id = f"test-{uuid4().hex[:8]}"
        task = asyncio.create_task(execute_test_run(run_id, options))
        test_tasks.add(task)
        task.add_done_callback(test_tasks.discard)
        run_ids.append(run_id)
    return {"runs": run_ids, "status": "started", "count": len(run_ids)}


@app.get("/api/tests/running")
async def list_running_tests():
    with tests_lock:
        active = list(running_tests.keys())
    return {"running": active, "count": len(active)}


@app.post("/api/tests/{run_id}/cancel")
async def cancel_test(run_id: str):
    with tests_lock:
        proc = running_tests.pop(run_id, None)
    if proc:
        poll = getattr(proc, "poll", None)
        returncode = poll() if callable(poll) else getattr(proc, "returncode", None)
        kill = getattr(proc, "kill", None)
        if returncode is None and callable(kill):
            kill()
        return {"status": "cancelled", "run_id": run_id}
    return {"status": "not_found", "run_id": run_id}


async def execute_test_run(run_id: str, options: TestRunOptions):
    """Run Maven tests, stream progress to WebSocket, and persist Allure results."""
    cmd = _test_command(options)
    started_at = datetime.now()
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(PROJECT_ROOT),
        env=_test_env(),
    )
    with tests_lock:
        running_tests[run_id] = proc  # type: ignore[assignment]

    stats = {
        "run_id": run_id,
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "running": 0,
        "scenarios": [],
        "output": [],
    }

    def update_last_running(status: str, count: int = 1) -> None:
        updated = 0
        for scenario in reversed(stats["scenarios"]):
            if scenario.get("status") == "running":
                scenario["status"] = status
                updated += 1
                if updated == count:
                    break

    async def publish() -> None:
        completed = stats["passed"] + stats["failed"] + stats["skipped"]
        expected = max(stats["total"], completed + stats["running"], 1)
        pct = round((completed / expected) * 100)
        await ws_manager.broadcast(run_id, {**stats, "pct": min(pct, 100), "type": "progress"})

    async def consume_stream(stream: asyncio.StreamReader | None) -> None:
        if stream is None:
            return
        async for line in stream:
            decoded = line.decode(errors="replace").strip()
            if not decoded:
                continue
            stats["output"].append(decoded)

            if "Scenario:" in decoded or "Scenario Outline:" in decoded:
                marker = "Scenario Outline:" if "Scenario Outline:" in decoded else "Scenario:"
                name = decoded.split(marker, 1)[-1].strip().split("#", 1)[0].strip()
                stats["total"] += 1
                stats["running"] += 1
                stats["scenarios"].append({"name": name, "status": "running"})
            elif "PASSED" in decoded and "Scenario" not in decoded:
                pass_count = max(decoded.count("PASSED"), 1)
                stats["passed"] += pass_count
                stats["running"] = max(0, stats["running"] - pass_count)
                update_last_running("passed", pass_count)
            elif "FAILED" in decoded:
                fail_count = max(decoded.count("FAILED"), 1)
                stats["failed"] += fail_count
                stats["running"] = max(0, stats["running"] - fail_count)
                update_last_running("failed", fail_count)
            elif "SKIPPED" in decoded:
                skip_count = max(decoded.count("SKIPPED"), 1)
                stats["skipped"] += skip_count
                stats["running"] = max(0, stats["running"] - skip_count)
                update_last_running("skipped", skip_count)

            await publish()

    try:
        await ws_manager.broadcast(run_id, {**stats, "pct": 0, "type": "progress"})
        await asyncio.gather(consume_stream(proc.stdout), consume_stream(proc.stderr))
        await proc.wait()
        saved = _save_results_to_duckdb(run_id, options, started_at)
        if saved:
            stats.update({"total": saved["total"], "passed": saved["passed"], "failed": saved["failed"], "skipped": saved["skipped"], "running": 0})
    finally:
        with tests_lock:
            running_tests.pop(run_id, None)

    completed = stats["passed"] + stats["failed"] + stats["skipped"]
    await ws_manager.broadcast(
        run_id,
        {
            **stats,
            "finished": True,
            "type": "complete",
            "exit_code": proc.returncode,
            "pct": 100 if completed or proc.returncode == 0 else 0,
        },
    )


def _save_results_to_duckdb(run_id: str, options: TestRunOptions, started_at: datetime | None = None) -> dict:
    """Parse allure-results JSON and insert run/scenario rows into DuckDB."""
    import hashlib

    allure_dir = PROJECT_ROOT / "test-core" / "target" / "allure-results"
    status_map = {
        "passed": "PASSED",
        "failed": "FAILED",
        "broken": "BROKEN",
        "skipped": "SKIPPED",
        "unknown": "UNKNOWN",
    }
    scenarios = []
    if allure_dir.exists():
        for result_file in sorted(allure_dir.glob("*-result.json")):
            try:
                data = json.loads(result_file.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            raw_status = str(data.get("status", "unknown")).lower()
            status = status_map.get(raw_status, "UNKNOWN")
            name = data.get("name") or "unknown"
            full_name = data.get("fullName") or ""
            feature_file = full_name.split(":", 1)[0].split(".", 1)[0] if full_name else ""
            time_data = data.get("time") or {}
            duration = (time_data.get("duration") or 0) / 1000
            error = ((data.get("statusDetails") or {}).get("message") or "")[:500]
            identity_key = data.get("historyId") or f"{feature_file}:{name}"
            scenario_uid = hashlib.sha256(str(identity_key).encode()).hexdigest()[:32]
            scenarios.append((scenario_uid, str(identity_key), name, status, duration, error, feature_file))

    passed = sum(1 for _, _, _, status, _, _, _ in scenarios if status == "PASSED")
    failed = sum(1 for _, _, _, status, _, _, _ in scenarios if status in {"FAILED", "BROKEN"})
    skipped = sum(1 for _, _, _, status, _, _, _ in scenarios if status == "SKIPPED")
    finished_at = datetime.now()

    conn = get_connection(read_only=False)
    try:
        init_schema(conn)
        conn.execute("DELETE FROM scenario_results WHERE run_id = ?", [run_id])
        run_values = [options.version, options.environment, started_at or finished_at, finished_at, len(scenarios), passed, failed, skipped, options.visibility, run_id]
        if conn.execute("SELECT 1 FROM runs WHERE id = ?", [run_id]).fetchone():
            conn.execute(
                """
                UPDATE runs
                SET version = ?, environment = ?, started_at = ?, finished_at = ?, total_scenarios = ?, passed = ?, failed = ?, skipped = ?, visibility = ?
                WHERE id = ?
                """,
                run_values,
            )
        else:
            conn.execute(
                """
                INSERT INTO runs
                (version, environment, started_at, finished_at, total_scenarios, passed, failed, skipped, visibility, id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                run_values,
            )
        for scenario_uid, identity_key, name, status, duration, error, feature_file in scenarios:
            if conn.execute("SELECT 1 FROM scenario_definitions WHERE scenario_uid = ?", [scenario_uid]).fetchone():
                conn.execute(
                    """
                    UPDATE scenario_definitions
                    SET identity_source = 'allure', identity_key = ?, current_name = ?, current_feature_file = ?, last_seen_run_id = ?, last_seen_at = ?, active = true
                    WHERE scenario_uid = ?
                    """,
                    [identity_key, name, feature_file, run_id, finished_at, scenario_uid],
                )
            else:
                conn.execute(
                    """
                    INSERT INTO scenario_definitions
                    (scenario_uid, identity_source, identity_key, current_name, current_feature_file, doors_number, first_seen_run_id, last_seen_run_id, first_seen_at, last_seen_at)
                    VALUES (?, 'allure', ?, ?, ?, NULL, ?, ?, ?, ?)
                    """,
                    [scenario_uid, identity_key, name, feature_file, run_id, run_id, started_at or finished_at, finished_at],
                )
            conn.execute(
                """
                INSERT INTO scenario_results
                (run_id, scenario_uid, name_at_run, status, duration_seconds, error_message, feature_file_at_run)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [run_id, scenario_uid, name, status, duration, error, feature_file],
            )
        # Also write manifest JSON for dashboard compatibility
        _write_manifest_json(run_id, options, scenarios, passed, failed, skipped, started_at or finished_at)
    finally:
        conn.close()

    return {"total": len(scenarios), "passed": passed, "failed": failed, "skipped": skipped}


def _write_manifest_json(run_id: str, options: TestRunOptions, scenarios: list, passed: int, failed: int, skipped: int, ts: datetime) -> None:
    manifest_dir = PROJECT_ROOT / "manifests"
    manifest_dir.mkdir(exist_ok=True)
    manifest_path = manifest_dir / f"{run_id}.json"
    total = len(scenarios)
    manifest = {
        "runId": run_id,
        "timestamp": ts.isoformat(),
        "totalScenarios": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "duration": "0.0s",
        "version": options.version or "",
        "environment": options.environment or "",
        "scenarios": [
            {
                "id": f"{run_id}-{i}",
                "name": name,
                "status": status.lower(),
                "duration": f"{duration:.1f}s",
                "doorsAbsNumber": None,
                "tags": [],
                "steps": [],
                "attachments": [],
                "attempts": [],
                "dependencies": [],
                "errorMessage": error or "",
            }
            for i, (_, _, name, status, duration, error, feature_file) in enumerate(scenarios)
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))


@app.get("/api/pipeline/status/{run_id}")
async def pipeline_status(run_id: str):
    conn = get_connection(read_only=False)
    try:
        init_schema(conn)
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
def list_runs(version: Optional[str] = None):
    manifests = load_manifests()
    # Enrich manifests that lack a version with DuckDB data
    needs_version = [m for m in manifests if not m.version]
    if needs_version:
        conn = get_connection(read_only=True)
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


@app.get("/api/v1/runs/{run_id}/bug-status", response_model=List)
def get_bug_statuses(run_id: str):
    manifest_path = MANIFESTS_DIR / f"{run_id}.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    manifest = json.loads(manifest_path.read_text())
    results = []
    for s in manifest.get("scenarios", []):
        doors = s.get("doorsAbsNumber")
        result = {
            "scenarioId": s.get("id", ""),
            "doorsAbsNumber": doors,
            "isReported": False,
        }
        if doors:
            bug = tracker.get(doors)
            if bug:
                result["jiraKey"] = bug.get("jiraKey")
                result["jiraUrl"] = jira_client.issue_url(bug["jiraKey"]) if jira_client.is_configured() else None
                result["status"] = bug.get("status")
                result["isReported"] = True
        results.append(result)
    return results


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


@app.get("/api/reports/merge-data")
async def reports_merge_data(run_ids: str = ""):
    """Return merged scenario data for selected run IDs (comma-separated)."""
    if not run_ids:
        return {"runs": [], "scenarios": [], "summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0}}
    ids = [r.strip() for r in run_ids.split(",") if r.strip()]
    manifests = load_manifests()
    selected = [m for m in manifests if m.runId in ids]
    all_scenarios = []
    for m in selected:
        for s in m.scenarios:
            all_scenarios.append({
                "runId": m.runId,
                "id": s.id,
                "name": s.name,
                "status": s.status,
                "duration": s.duration,
                "tags": s.tags,
                "steps": [{"name": st.name, "status": st.status, "errorMessage": st.errorMessage} for st in s.steps],
                "errorMessage": s.steps[0].errorMessage if s.steps and s.status == "failed" and any(st.errorMessage for st in s.steps) else None,
            })
    summary = {
        "total": len(all_scenarios),
        "passed": sum(1 for s in all_scenarios if s["status"] == "passed"),
        "failed": sum(1 for s in all_scenarios if s["status"] == "failed"),
        "skipped": sum(1 for s in all_scenarios if s["status"] == "skipped"),
    }
    return {"runs": [{"runId": m.runId, "timestamp": str(m.timestamp), "totalScenarios": m.totalScenarios, "passed": m.passed, "failed": m.failed, "skipped": m.skipped} for m in selected], "scenarios": all_scenarios, "summary": summary}


def sync_runs() -> dict:
    """Backfill both data stores:
    - Manifest files without a DuckDB row → insert into DuckDB
    - DuckDB runs without a manifest file → create manifest JSON
    Safe to call repeatedly (skips already-synced entries).
    """
    import hashlib

    manifests = load_manifests()
    manifest_by_id = {m.runId: m for m in manifests}

    _status_down = {"PASSED": "passed", "FAILED": "failed", "SKIPPED": "skipped",
                    "BROKEN": "failed", "UNKNOWN": "skipped"}

    conn = get_connection(read_only=False)
    try:
        init_schema(conn)
        db_runs = {r[0]: {"version": r[1], "environment": r[2], "started_at": r[3],
                          "finished_at": r[4], "total": r[5], "passed": r[6],
                          "failed": r[7], "skipped": r[8]}
                   for r in conn.execute(
                       "SELECT id, version, environment, started_at, finished_at, "
                       "total_scenarios, passed, failed, skipped FROM runs"
                   ).fetchall()}

        inserted_to_db = 0
        created_manifests = 0

        # 1. Manifests → DuckDB
        for run_id, m in manifest_by_id.items():
            if run_id not in db_runs:
                ts = m.timestamp or datetime.now()
                conn.execute(
                    """INSERT INTO runs (id, version, environment, started_at, finished_at,
                       total_scenarios, passed, failed, skipped, visibility)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'internal')""",
                    [run_id, m.version or None, m.environment or None,
                     ts, ts, m.totalScenarios, m.passed, m.failed, m.skipped],
                )
                for i, s in enumerate(m.scenarios):
                    uid = hashlib.sha256(f"{run_id}:{s.name}:{i}".encode()).hexdigest()[:32]
                    if not conn.execute(
                        "SELECT 1 FROM scenario_definitions WHERE scenario_uid = ?", [uid]
                    ).fetchone():
                        conn.execute(
                            """INSERT INTO scenario_definitions
                               (scenario_uid, identity_source, identity_key, current_name,
                                first_seen_run_id, last_seen_run_id, first_seen_at, last_seen_at)
                               VALUES (?, 'manifest', ?, ?, ?, ?, ?, ?)""",
                            [uid, f"{run_id}:{s.name}", s.name, run_id, run_id, ts, ts],
                        )
                    conn.execute(
                        """INSERT INTO scenario_results
                           (run_id, scenario_uid, name_at_run, status, duration_seconds,
                            error_message, feature_file_at_run)
                           VALUES (?, ?, ?, ?, ?, ?, '')""",
                        [run_id, uid, s.name, s.status.upper(), 0.0, None],
                    )
                inserted_to_db += 1

        # 2. DuckDB → manifests (create new + refresh existing ones with empty scenario tags)
        for run_id, run_data in db_runs.items():
            existing = manifest_by_id.get(run_id)
            needs_tag_refresh = existing and existing.scenarios and not any(
                s.tags for s in existing.scenarios
            )
            if run_id not in manifest_by_id or needs_tag_refresh:
                scenario_rows = conn.execute(
                    "SELECT name_at_run, status, duration_seconds, error_message, "
                    "COALESCE(feature_file_at_run, '') "
                    "FROM scenario_results WHERE run_id = ? ORDER BY id",
                    [run_id],
                ).fetchall()
                ts = run_data["started_at"] or (existing.timestamp if existing else datetime.now())
                ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                total = run_data["total"] or len(scenario_rows)
                scenarios = [
                    {"id": f"{run_id}-{i}", "name": row[0],
                     "status": _status_down.get(row[1], "skipped"),
                     "duration": f"{(row[2] or 0):.1f}s",
                     "doorsAbsNumber": None,
                     "tags": [row[4]] if row[4] else [],
                     "steps": [], "attachments": [], "attempts": [], "dependencies": [],
                     "errorMessage": row[3] or ""}
                    for i, row in enumerate(scenario_rows)
                ]
                manifest_data = {
                    "runId": run_id,
                    "timestamp": ts_str,
                    "totalScenarios": total,
                    "passed": run_data["passed"] or 0,
                    "failed": run_data["failed"] or 0,
                    "skipped": run_data["skipped"] or 0,
                    "duration": existing.duration if existing else "0.0s",
                    "version": run_data["version"] or (existing.version if existing else "") or "",
                    "environment": run_data["environment"] or (existing.environment if existing else "") or "",
                    "scenarios": scenarios,
                }
                manifest_path = MANIFESTS_DIR / f"{run_id}.json"
                manifest_path.write_text(json.dumps(manifest_data, indent=2, default=str))
                if run_id not in manifest_by_id:
                    created_manifests += 1
    finally:
        conn.close()

    return {"inserted_to_db": inserted_to_db, "created_manifests": created_manifests}


@app.post("/api/admin/sync-runs", dependencies=[Depends(verify_token)])
def admin_sync_runs():
    """Backfill manifests ↔ DuckDB so version filters work across all historical runs."""
    return sync_runs()


@app.get("/api/versions")
async def get_versions():
    conn = get_connection(read_only=False)
    try:
        init_schema(conn)
        rows = conn.execute(
            "SELECT DISTINCT version FROM runs WHERE version IS NOT NULL ORDER BY version DESC"
        ).fetchall()
        return {"versions": [r[0] for r in rows]}
    finally:
        conn.close()


@app.get("/api/dashboard/metrics")
async def dashboard_metrics(
    version: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    conn = get_connection(read_only=True)
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


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    template = jinja_env.get_template("dashboard.html")
    return HTMLResponse(content=template.render())


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    template = jinja_env.get_template("admin.html")
    return HTMLResponse(content=template.render())


@app.get("/reports/merge", response_class=HTMLResponse)
async def report_merge_page(request: Request):
    template = jinja_env.get_template("report-merge.html")
    return HTMLResponse(content=template.render())


@app.get("/reports/{run_id}", response_class=HTMLResponse)
def run_detail(run_id: str, request: Request):
    # Check public visibility first (no auth required)
    conn = get_connection(read_only=False)
    try:
        init_schema(conn)
        run_row = conn.execute(
            "SELECT id, visibility FROM runs WHERE id = ?", [run_id]
        ).fetchone()
        if run_row and run_row[1] == "public":
            # Public report — no auth needed
            scenarios = conn.execute(
                "SELECT name_at_run, status, duration_seconds FROM scenario_results WHERE run_id = ?",
                [run_id],
            ).fetchall()
            template = jinja_env.get_template("public_report.html")
            html = template.render(
                run_id=run_id,
                scenarios=scenarios,
            )
            return HTMLResponse(content=html)
    except Exception:
        pass
    finally:
        conn.close()

    # Fall back to manifest-based detail (requires auth for non-public)
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
        issue = jira_client.create_issue(summary, description)
        key = issue["key"] if isinstance(issue, dict) else issue
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


class DoorsRunRequest(BaseModel):
    script: str


@app.post("/api/doors/run")
async def doors_run(req: DoorsRunRequest):
    if not is_doors_available():
        return {"status": "unavailable", "message": "DOORS not installed"}
    code, out, err = run_doors_dxl(req.script)
    return {"status": "success" if code == 0 else "failed", "stdout": out, "stderr": err}


@app.post("/api/email/send")
async def email_send(to: str, run_id: str):
    context = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "started_at": "",
        "dashboard_url": f"http://localhost:8000/reports/{run_id}",
    }
    try:
        send_email(to, f"Test Raporu - {run_id}", "test_report.html", context)
        return {"sent": True}
    except Exception as e:
        return {"sent": False, "error": str(e)}


@app.websocket("/ws/test-status/{run_id}")
async def test_status_ws(websocket: WebSocket, run_id: str):
    await ws_manager.connect(run_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "start":
                await stream_test_output(run_id)
    except WebSocketDisconnect:
        ws_manager.disconnect(run_id, websocket)


MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/reports", StaticFiles(directory=str(MANIFESTS_DIR)), name="reports")
app.mount("/static", StaticFiles(directory="static"), name="static")
