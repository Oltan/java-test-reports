import json
import csv
import io
import os
import re
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
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

from models import RunManifest, ScenarioResult, TestRunOptions
from bug_tracker import BugTracker
from db import get_connection, init_schema, upsert_scenario_history, update_scenario_history_explanation, get_scenario_history, get_scenario_matrix
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


def _log_task_exception(task: asyncio.Task) -> None:
    if task.done() and not task.cancelled():
        exc = task.exception()
        if exc is not None:
            import traceback
            print(f"[ERROR] Background task failed: {exc}")
            traceback.print_exception(type(exc), exc, exc.__traceback__)


def load_manifests() -> list[RunManifest]:
    if not MANIFESTS_DIR.exists():
        return []
    manifests = []
    for f in sorted(MANIFESTS_DIR.glob("*.json")):
        with open(f) as fh:
            data = json.load(fh)
        manifests.append(RunManifest.model_validate(data))
    return manifests


tracker = BugTracker(str(Path(__file__).parent.parent / "bug-tracker.json"))
jira_client = JiraClient()

app = FastAPI(title="Test Reports API", version="1.0.0")
app.include_router(tfs_router)

jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
jinja_env.tests["contains"] = lambda value, item: item in value if value else False

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()


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


def verify_token_page(request: Request) -> TokenData:
    """Auth dependency for HTML pages: checks cookie first, then Authorization header.
    Redirects to login page on failure instead of returning 401 JSON."""
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": "/"},
        )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/"})
        return TokenData(username=username)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/"})


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


@app.post("/api/pipeline/run", dependencies=[Depends(verify_token)])
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
    # Windows: mvn.cmd is the standard wrapper
    win_mvn = shutil.which("mvn.cmd") or shutil.which("mvn")
    return win_mvn or "mvn"


def _test_command(options: TestRunOptions, output_dir: str | None = None) -> list[str]:
    cmd = [
        _maven_executable(),
        "-pl", "test-core",
        "test",
        f"-Dcucumber.filter.tags={options.tags}",
    ]
    if options.retry_count:
        cmd.append(f"-Dretry.count={options.retry_count}")
    if output_dir:
        cmd.append(f"-Dallure.results.directory={output_dir}")
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


@app.post("/api/tests/start", dependencies=[Depends(verify_token)])
async def start_tests(options: TestRunOptions, background_tasks: BackgroundTasks):
    """Start tests with validated options. Invalid options are rejected by Pydantic."""
    del background_tasks
    job_id = f"job-{uuid4().hex[:8]}"
    now = datetime.now()
    run_ids = []
    workers = []

    with get_connection(read_only=False) as conn:
        init_schema(conn)
        conn.execute(
            """
            INSERT INTO jobs (job_id, requester, tags, retry_count, parallel, environment, version, status, started_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?)
            """,
            [job_id, "engineer", options.tags, options.retry_count, options.parallel,
             options.environment, options.version, now],
        )

        for i in range(options.parallel):
            run_id = f"test-{uuid4().hex[:8]}"
            worker_id = f"{job_id}-w{i}"
            output_dir = str(PROJECT_ROOT / "test-core" / "target" / f"allure-results-{run_id}")
            conn.execute(
                """
                INSERT INTO worker_runs (worker_id, job_id, run_id, shard, status, output_dir, started_at)
                VALUES (?, ?, ?, ?, 'running', ?, ?)
                """,
                [worker_id, job_id, run_id, i, output_dir, now],
            )
            run_ids.append(run_id)
            workers.append({"worker_id": worker_id, "run_id": run_id, "shard": i, "output_dir": output_dir})

        conn.commit()

    if options.parallel > 1:
        for run_id, worker in zip(run_ids, workers):
            task = asyncio.create_task(execute_test_run(run_id, options, output_dir=worker["output_dir"]))
            test_tasks.add(task)
            task.add_done_callback(lambda t: test_tasks.discard(t))
            task.add_done_callback(_log_task_exception)
    else:
        for run_id in run_ids:
            task = asyncio.create_task(execute_test_run(run_id, options))
            test_tasks.add(task)
            task.add_done_callback(lambda t: test_tasks.discard(t))
            task.add_done_callback(_log_task_exception)

    return {"job_id": job_id, "workers": workers, "runs": run_ids, "status": "started", "mode": "serialized_safe", "parallel": options.parallel}


@app.get("/api/tests/running", dependencies=[Depends(verify_token)])
async def list_running_tests():
    with get_connection(read_only=False) as conn:
        init_schema(conn)
        rows = conn.execute(
            """
            SELECT j.job_id, j.tags, j.retry_count, j.parallel, j.environment, j.version, j.started_at,
                   w.worker_id, w.run_id, w.shard, w.status as worker_status, w.output_dir
            FROM jobs j
            JOIN worker_runs w ON j.job_id = w.job_id
            WHERE j.status = 'running'
            ORDER BY j.started_at DESC
            """
        ).fetchall()
    if not rows:
        return {"running": [], "jobs": [], "count": 0}
    jobs_map = {}
    for row in rows:
        job_id = row[0]
        if job_id not in jobs_map:
            jobs_map[job_id] = {
                "job_id": job_id,
                "tags": row[1],
                "retry_count": row[2],
                "parallel": row[3],
                "environment": row[4],
                "version": row[5],
                "started_at": row[6].isoformat() if row[6] else None,
                "workers": [],
            }
        jobs_map[job_id]["workers"].append({
            "worker_id": row[7],
            "run_id": row[8],
            "shard": row[9],
            "status": row[10],
            "output_dir": row[11],
        })
    jobs = list(jobs_map.values())
    return {"running": list(jobs_map.keys()), "jobs": jobs, "count": len(jobs)}


@app.get("/api/tests/jobs", dependencies=[Depends(verify_token)])
async def list_all_jobs():
    with get_connection(read_only=False) as conn:
        init_schema(conn)
        rows = conn.execute(
            """
            SELECT j.job_id, j.tags, j.retry_count, j.parallel, j.environment, j.version,
                   j.status, j.started_at, j.ended_at,
                   w.worker_id, w.run_id, w.shard, w.status as worker_status, w.output_dir
            FROM jobs j
            JOIN worker_runs w ON j.job_id = w.job_id
            ORDER BY j.started_at DESC
            """
        ).fetchall()
        if not rows:
            return {"jobs": [], "count": 0}
        jobs_map = {}
        for row in rows:
            job_id = row[0]
            if job_id not in jobs_map:
                jobs_map[job_id] = {
                    "job_id": job_id,
                    "tags": row[1],
                    "retry_count": row[2],
                    "parallel": row[3],
                    "environment": row[4],
                    "version": row[5],
                    "status": row[6],
                    "started_at": row[7].isoformat() if row[7] else None,
                    "ended_at": row[8].isoformat() if row[8] else None,
                    "workers": [],
                }
            jobs_map[job_id]["workers"].append({
                "worker_id": row[9],
                "run_id": row[10],
                "shard": row[11],
                "status": row[12],
                "output_dir": row[13],
            })
        jobs = list(jobs_map.values())
        for job in jobs:
            run_ids = [w["run_id"] for w in job["workers"]]
            flaky_count = 0
            retry_total = 0
            if run_ids:
                placeholders = ",".join(["?"] * len(run_ids))
                flaky_row = conn.execute(
                    f"SELECT COUNT(*) FROM scenario_results WHERE run_id IN ({placeholders}) AND retry_attempt > 1",
                    run_ids,
                ).fetchone()
                retry_total = flaky_row[0] if flaky_row else 0
                flaky_row2 = conn.execute(
                    f"""
                    SELECT COUNT(DISTINCT sr.scenario_uid) FROM scenario_results sr
                    WHERE sr.run_id IN ({placeholders})
                    AND sr.scenario_uid IN (
                        SELECT DISTINCT sr2.scenario_uid FROM scenario_results sr2
                        WHERE sr2.run_id IN ({placeholders}) AND sr2.retry_attempt > 1 AND sr2.status IN ('PASSED',)
                    )
                    AND sr.status IN ('FAILED','BROKEN')
                    """,
                    run_ids + run_ids,
                ).fetchone()
                flaky_count = flaky_row2[0] if flaky_row2 else 0
            job["flaky_count"] = flaky_count
            job["retry_total"] = retry_total
    return {"jobs": jobs, "count": len(jobs)}


@app.post("/api/tests/{run_id}/cancel", dependencies=[Depends(verify_token)])
async def cancel_test(run_id: str):
    now = datetime.now()
    with get_connection(read_only=False) as conn:
        worker_row = conn.execute(
            "SELECT worker_id, job_id FROM worker_runs WHERE run_id = ?",
            [run_id],
        ).fetchone()
        if not worker_row:
            return {"status": "not_found", "run_id": run_id}
        worker_id, job_id = worker_row[0], worker_row[1]

        # Cancel all workers belonging to the same job (serialized job)
        conn.execute(
            "UPDATE worker_runs SET status = 'cancelled', ended_at = ? WHERE job_id = ?",
            [now, job_id],
        )
        conn.execute(
            "UPDATE jobs SET status = 'cancelled', ended_at = ? WHERE job_id = ?",
            [now, job_id],
        )
        conn.commit()

    with tests_lock:
        # Kill all running processes for this job
        cancelled_run_ids = []
        for rid, proc in list(running_tests.items()):
            # Find run_id by checking if it's in this job
            worker_row_check = conn.execute(
                "SELECT run_id FROM worker_runs WHERE run_id = ? AND job_id = ?",
                [rid, job_id],
            ).fetchone()
            if worker_row_check:
                poll = getattr(proc, "poll", None)
                returncode = poll() if callable(poll) else getattr(proc, "returncode", None)
                kill = getattr(proc, "kill", None)
                if returncode is None and callable(kill):
                    kill()
                cancelled_run_ids.append(rid)
        for rid in cancelled_run_ids:
            running_tests.pop(rid, None)

    return {"status": "cancelled", "run_id": run_id, "job_id": job_id}


@app.post("/api/tests/job/{job_id}/cancel", dependencies=[Depends(verify_token)])
async def cancel_job(job_id: str):
    now = datetime.now()
    with get_connection(read_only=False) as conn:
        job_row = conn.execute("SELECT job_id FROM jobs WHERE job_id = ?", [job_id]).fetchone()
        if not job_row:
            return {"status": "not_found", "job_id": job_id}
        conn.execute(
            "UPDATE worker_runs SET status = 'cancelled', ended_at = ? WHERE job_id = ?",
            [now, job_id],
        )
        conn.execute(
            "UPDATE jobs SET status = 'cancelled', ended_at = ? WHERE job_id = ?",
            [now, job_id],
        )
        conn.commit()

        worker_run_ids = [r[0] for r in conn.execute(
            "SELECT run_id FROM worker_runs WHERE job_id = ?",
            [job_id],
        ).fetchall()]

    with tests_lock:
        for rid in worker_run_ids:
            proc = running_tests.pop(rid, None)
            if proc:
                poll = getattr(proc, "poll", None)
                returncode = poll() if callable(poll) else getattr(proc, "returncode", None)
                kill = getattr(proc, "kill", None)
                if returncode is None and callable(kill):
                    kill()

    return {"status": "cancelled", "job_id": job_id}


async def execute_test_run(run_id: str, options: TestRunOptions, output_dir: str | None = None):
    """Run Maven tests, stream progress to WebSocket, and persist Allure results."""
    cmd = _test_command(options, output_dir=output_dir)
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
    except Exception as e:
        import traceback
        print(f"[ERROR] execute_test_run {run_id}: {e}")
        traceback.print_exc()
        stats["error"] = str(e)
        stats["running"] = 0
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
            "exit_code": getattr(proc, "returncode", -1),
            "pct": 100 if completed or getattr(proc, "returncode", -1) == 0 else 0,
        },
    )

    now = datetime.now()
    final_status = "completed" if not stats.get("error") else "failed"
    with get_connection(read_only=False) as conn:
        conn.execute(
            "UPDATE worker_runs SET status = ?, ended_at = ? WHERE run_id = ?",
            [final_status, now, run_id],
        )
        pending_row = conn.execute(
            "SELECT COUNT(*) FROM worker_runs WHERE job_id = (SELECT job_id FROM worker_runs WHERE run_id = ?) AND status = 'running'",
            [run_id],
        ).fetchone()
        pending = pending_row[0] if pending_row else 0
        if pending == 0:
            job_row = conn.execute(
                "SELECT job_id FROM worker_runs WHERE run_id = ?",
                [run_id],
            ).fetchone()
            if job_row:
                conn.execute(
                    "UPDATE jobs SET status = ?, ended_at = ? WHERE job_id = ?",
                    [final_status, now, job_row[0]],
                )
        conn.commit()


def _parse_allure_result(result_file: Path) -> dict | None:
    """Parse a single Allure result JSON file and extract full metadata."""
    try:
        data = json.loads(result_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    # Extract status
    raw_status = str(data.get("status", "unknown")).lower()
    status_map = {
        "passed": "PASSED",
        "failed": "FAILED",
        "broken": "BROKEN",
        "skipped": "SKIPPED",
        "unknown": "UNKNOWN",
    }
    status = status_map.get(raw_status, "UNKNOWN")

    name = data.get("name") or "unknown"
    full_name = data.get("fullName") or ""
    feature_file = full_name.split(":", 1)[0].split(".", 1)[0] if full_name else ""

    time_data = data.get("time") or {}
    duration = (time_data.get("duration") or 0) / 1000
    error = ((data.get("statusDetails") or {}).get("message") or "")[:500]
    identity_key = data.get("historyId") or f"{feature_file}:{name}"

    # Parse labels for tags (mimics Java AllureResultsParser.parseTags)
    labels = data.get("labels") or []
    tags = []
    doors_id = None
    dependencies = []
    for label in labels:
        if not isinstance(label, dict):
            continue
        label_name = label.get("name") or ""
        label_value = label.get("value") or ""
        if label_name == "tag":
            tag_str = str(label_value).strip()
            doors_match = re.search(r"@?(?:DOORS-\d+|ABS-\d+)", tag_str, re.IGNORECASE)
            if doors_match:
                doors_id = doors_match.group(0).lstrip("@")
            else:
                dep_match = re.match(r"@dep:(.+)", tag_str, re.IGNORECASE)
                if dep_match:
                    dependencies.append(dep_match.group(1).strip())
                else:
                    tags.append(tag_str)
        elif label_name == "suite":
            pass

    retry_attempt = 1
    history_id = data.get("historyId") or ""
    retry_match = re.search(r"--retry-(\d+)", history_id)
    if not retry_match:
        retry_match = re.search(r"--retry-(\d+)", name)
    if retry_match:
        retry_attempt = int(retry_match.group(1))

    # Timestamp from Allure start time
    start_ts = data.get("start")
    ts_str = datetime.fromtimestamp(start_ts / 1000).isoformat() if start_ts else datetime.now().isoformat()

    # Build AttemptResult
    attempt = {"status": raw_status, "timestamp": ts_str, "errorMessage": error or None}

    # Parse steps
    steps = []
    for step in data.get("steps") or []:
        step_status = str(step.get("status") or "unknown").lower()
        step_error = ((step.get("statusDetails") or {}).get("message") or "")[:300]
        steps.append({
            "name": step.get("name") or "",
            "status": step_status,
            "errorMessage": step_error or None,
        })

    return {
        "identity_key": identity_key,
        "name": name,
        "status": status,
        "status_raw": raw_status,
        "duration": duration,
        "error": error,
        "feature_file": feature_file,
        "tags": tags,
        "doors_id": doors_id,
        "dependencies": dependencies,
        "retry_attempt": retry_attempt,
        "attempt": attempt,
        "steps": steps,
    }


def _save_results_to_duckdb(run_id: str, options: TestRunOptions, started_at: datetime | None = None) -> dict:
    """Parse allure-results JSON and insert run/scenario rows into DuckDB."""
    import hashlib

    allure_dir = Path(os.getenv("ALLURE_RESULTS_DIR", str(PROJECT_ROOT / "test-core" / "target" / "allure-results")))
    print(f"[INFO] allure_dir={allure_dir}  exists={allure_dir.exists()}")
    if allure_dir.exists():
        files = list(allure_dir.glob("*-result.json"))
        print(f"[INFO] result files found: {len(files)}")

    # Group results by identity_key to detect retries (multiple attempts)
    grouped: dict[str, list[dict]] = {}
    all_scenarios = []

    DEP_TAG_RE = re.compile(r"@dep:(.+)", re.IGNORECASE)

    if allure_dir.exists():
        for result_file in sorted(allure_dir.glob("*-result.json")):
            parsed = _parse_allure_result(result_file)
            if parsed is None:
                continue

            key = parsed["identity_key"]
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(parsed)

    # Build scenarios list with attempt tracking
    scenario_map: dict[str, dict] = {}
    for key, attempts in grouped.items():
        # Sort by retry_attempt then timestamp
        attempts_sorted = sorted(attempts, key=lambda a: (a["retry_attempt"], a["attempt"]["timestamp"]))
        final = attempts_sorted[-1]

        # Flaky = final passed but earlier attempt failed
        is_flaky = False
        if final["status"] == "PASSED" and len(attempts_sorted) > 1:
            is_flaky = any(a["status_raw"] in ("failed", "broken") for a in attempts_sorted[:-1])

        # Build attempt list (only include when >1 or is_flaky to avoid clutter)
        attempt_list = []
        if is_flaky or len(attempts_sorted) > 1:
            attempt_list = [a["attempt"] for a in attempts_sorted]

        scenario_uid = hashlib.sha256(str(key).encode()).hexdigest()[:32]

        scenario_map[key] = {
            "uid": scenario_uid,
            "identity_key": key,
            "name": final["name"],
            "status": final["status"],
            "duration": final["duration"],
            "error": final["error"],
            "feature_file": final["feature_file"],
            "tags": final["tags"],
            "doors_id": final["doors_id"],
            "dependencies": final["dependencies"],
            "retry_attempt": final["retry_attempt"],
            "is_flaky": is_flaky,
            "attempt_list": attempt_list,
            "total_attempts": len(attempts_sorted),
        }
        all_scenarios.append(scenario_map[key])

    # Count statuses
    passed = sum(1 for s in all_scenarios if s["status"] == "PASSED")
    failed = sum(1 for s in all_scenarios if s["status"] in {"FAILED", "BROKEN"})
    skipped = sum(1 for s in all_scenarios if s["status"] == "SKIPPED")
    finished_at = datetime.now()

    conn = get_connection(read_only=False)
    try:
        init_schema(conn)
        conn.execute("DELETE FROM scenario_results WHERE run_id = ?", [run_id])
        run_values = [options.version, options.environment, started_at or finished_at, finished_at, len(all_scenarios), passed, failed, skipped, options.visibility, run_id]
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
        for s in all_scenarios:
            # Upsert scenario_definitions
            existing_def = conn.execute("SELECT 1 FROM scenario_definitions WHERE scenario_uid = ?", [s["uid"]]).fetchone()
            if existing_def:
                conn.execute(
                    """
                    UPDATE scenario_definitions
                    SET identity_source = 'allure', identity_key = ?, current_name = ?, current_feature_file = ?, doors_number = COALESCE(?, doors_number), last_seen_run_id = ?, last_seen_at = ?, active = true
                    WHERE scenario_uid = ?
                    """,
                    [s["identity_key"], s["name"], s["feature_file"], s["doors_id"], run_id, finished_at, s["uid"]],
                )
            else:
                conn.execute(
                    """
                    INSERT INTO scenario_definitions
                    (scenario_uid, identity_source, identity_key, current_name, current_feature_file, doors_number, first_seen_run_id, last_seen_run_id, first_seen_at, last_seen_at)
                    VALUES (?, 'allure', ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [s["uid"], s["identity_key"], s["name"], s["feature_file"], s["doors_id"], run_id, run_id, started_at or finished_at, finished_at],
                )
            # Insert scenario_results with retry metadata
            conn.execute(
                """
                INSERT INTO scenario_results
                (run_id, scenario_uid, name_at_run, status, duration_seconds, error_message, feature_file_at_run, doors_number_at_run, retry_attempt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [run_id, s["uid"], s["name"], s["status"], s["duration"], s["error"], s["feature_file"], s["doors_id"], s["total_attempts"]],
            )
            if s.get("doors_id"):
                upsert_scenario_history(
                    conn,
                    doors_number=s["doors_id"],
                    scenario_uid=s["uid"],
                    name=s["name"],
                    run_id=run_id,
                    status=s["status"],
                    version=options.version,
                    timestamp=started_at or finished_at,
                )
        # Write manifest JSON with full metadata
        _write_manifest_json(run_id, options, all_scenarios, passed, failed, skipped, started_at or finished_at)
    finally:
        conn.close()

    return {"total": len(all_scenarios), "passed": passed, "failed": failed, "skipped": skipped}


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
                "name": s["name"],
                "status": s["status"].lower(),
                "duration": f"{s['duration']:.1f}s",
                "doorsAbsNumber": s.get("doors_id"),
                "tags": s.get("tags", []),
                "steps": s.get("steps", []),
                "attachments": [],
                "attempts": s.get("attempt_list", []),
                "dependencies": s.get("dependencies", []),
                "is_flaky": s.get("is_flaky", False),
                "errorMessage": s.get("error") or "",
            }
            for i, s in enumerate(scenarios)
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))


@app.get("/api/pipeline/status/{run_id}", dependencies=[Depends(verify_token)])
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
def login(req: LoginRequest, response: Response):
    if req.username != ADMIN_USERNAME or req.password != ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token = create_token(req.username)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=False,
        max_age=JWT_EXPIRATION_HOURS * 3600,
        samesite="lax",
        path="/",
    )
    return LoginResponse(token=token)


@app.websocket("/ws/test-status/live")
async def ws_test_status(websocket: WebSocket, token: str = Query(...)):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("sub") is None:
            await websocket.close(code=4001)
            return
    except jwt.InvalidTokenError:
        await websocket.close(code=4001)
        return

    await ws_manager.connect("live", websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect("live", websocket)


@app.websocket("/ws/test-status/{run_id}")
async def ws_test_run(websocket: WebSocket, run_id: str, token: str = Query(...)):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("sub") is None:
            await websocket.close(code=4001)
            return
    except jwt.InvalidTokenError:
        await websocket.close(code=4001)
        return

    await ws_manager.connect(run_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(run_id, websocket)


@app.get("/api/v1/runs", response_model=List[RunManifest])
def list_runs(version: Optional[str] = None):
    manifests = load_manifests()
    # Enrich manifests that lack a version with DuckDB data
    needs_version = [m for m in manifests if not m.version]
    if needs_version:
        conn = get_connection(read_only=False)
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
            return [s for s in m.scenarios if s.status in ("failed", "broken")]
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


@app.get("/api/scenario-history", dependencies=[Depends(verify_token)])
def list_scenario_history():
    conn = get_connection(read_only=True)
    try:
        init_schema(conn)
        return get_scenario_history(conn)
    finally:
        conn.close()


@app.get("/api/scenario-history/{doors_number}", dependencies=[Depends(verify_token)])
def get_scenario_history_item(doors_number: str):
    conn = get_connection(read_only=True)
    try:
        init_schema(conn)
        result = get_scenario_history(conn, doors_number)
        if not result:
            raise HTTPException(status_code=404, detail=f"DOORS number '{doors_number}' not found")
        return result
    finally:
        conn.close()


@app.get("/api/scenario-matrix", dependencies=[Depends(verify_token)])
def list_scenario_matrix(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    conn = get_connection(read_only=True)
    try:
        init_schema(conn)
        return get_scenario_matrix(conn, limit, offset)
    finally:
        conn.close()


@app.get("/api/reports/merge-data", dependencies=[Depends(verify_token)])
async def reports_merge_data(run_ids: str = ""):
    """Return merged scenario data for selected run IDs (comma-separated)."""
    if not run_ids:
        return {"runs": [], "scenarios": [], "summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0}}
    ids = [r.strip() for r in run_ids.split(",") if r.strip()]
    manifests = load_manifests()
    selected = [m for m in manifests if m.runId in ids]

    # Build a positional map {(run_id, index): scenario_uid} from the DB so the
    # frontend can pass the right uid to /api/reports/generate-share.
    uid_map: dict[tuple[str, int], str] = {}
    try:
        conn = get_connection(read_only=False)
        init_schema(conn)
        placeholders = ",".join(["?"] * len(ids))
        uid_rows = conn.execute(
            f"""
            SELECT run_id, scenario_uid,
                   ROW_NUMBER() OVER (PARTITION BY run_id ORDER BY rowid) - 1 AS pos
            FROM scenario_results
            WHERE run_id IN ({placeholders})
            """,
            ids,
        ).fetchall()
        conn.close()
        uid_map = {(r[0], int(r[2])): r[1] for r in uid_rows}
    except Exception:
        pass

    all_scenarios = []
    for m in selected:
        for i, s in enumerate(m.scenarios):
            all_scenarios.append({
                "runId": m.runId,
                "id": s.id,
                "scenario_uid": uid_map.get((m.runId, i)),
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


class GenerateShareRequest(BaseModel):
    scenario_ids: List[str]
    title: str = "Public Report"


@app.post("/api/reports/generate-share", dependencies=[Depends(verify_token)])
async def generate_public_share(req: GenerateShareRequest):
    """Create a public snapshot for selected scenario IDs (engineer-only).
    Blocked if any failed scenario lacks Jira ticket or override."""
    if not req.scenario_ids:
        raise HTTPException(status_code=422, detail="scenario_ids cannot be empty")

    conn = get_connection(read_only=False)
    try:
        init_schema(conn)

        # IDs arrive as "run_id:scenario_uid:status" (3-part), "run_id:scenario_uid" (2-part),
        # or plain scenario_uid. Run IDs and scenario_uids never contain ":", so splitting
        # into at most 3 parts on ":" is safe.
        def _parse_id(raw: str):
            parts = raw.split(":", 2)
            if len(parts) == 3:
                return parts[0], parts[1], parts[2]   # run_id, scenario_uid, manifest_status
            if len(parts) == 2:
                return parts[0], parts[1], None
            return None, raw, None

        parsed = [_parse_id(sid) for sid in req.scenario_ids]
        scenario_uids = [uid for _, uid, _ in parsed]

        blockers = []
        for run_id, scenario_uid, manifest_status in parsed:
            # Trust the manifest status when it was encoded in the compound ID.
            if manifest_status and manifest_status.upper() not in {"FAILED", "BROKEN"}:
                continue  # passed / skipped — no triage needed

            # No manifest status: query DB to determine status.
            if run_id:
                status_row = conn.execute(
                    "SELECT status FROM scenario_results WHERE run_id = ? AND scenario_uid = ? LIMIT 1",
                    [run_id, scenario_uid],
                ).fetchone()
            else:
                status_row = conn.execute(
                    "SELECT status FROM scenario_results WHERE scenario_uid = ? LIMIT 1",
                    [scenario_uid],
                ).fetchone()

            if not status_row or status_row[0] not in {"FAILED", "BROKEN"}:
                continue  # passed / skipped — no triage needed

            # Failed instance: check for triage decision
            triage_row = conn.execute(
                "SELECT decision FROM triage_decisions WHERE scenario_uid = ? LIMIT 1",
                [scenario_uid],
            ).fetchone()
            if not triage_row:
                blockers.append({
                    "scenario_id": scenario_uid,
                    "reason": "No triage decision — must be linked to Jira or accepted via override",
                })
            elif triage_row[0] not in {"jira_linked", "jira_created", "accepted_pass", "accepted_skip"}:
                blockers.append({
                    "scenario_id": scenario_uid,
                    "reason": f"Triage decision is '{triage_row[0]}' — must be Jira-linked or overridden",
                })

        if blockers:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Cannot generate public share — un triaged failures found",
                    "blockers": blockers,
                },
            )

        scenario_rows = []
        for run_id, scenario_uid, _ in parsed:
            if run_id:
                row = conn.execute("""
                    SELECT sr.scenario_uid, sr.name_at_run, sr.status, sr.duration_seconds,
                           sr.error_message, sd.current_name,
                           COALESCE(sr.doors_number_at_run, sd.doors_number) AS doors_number,
                           COALESCE(
                               sr.jira_key_at_run,
                               (SELECT jm.jira_key FROM jira_mappings jm WHERE jm.scenario_uid = sr.scenario_uid LIMIT 1),
                               (SELECT bm.jira_key FROM bug_mappings bm WHERE bm.doors_number = COALESCE(sr.doors_number_at_run, sd.doors_number) LIMIT 1)
                           ) AS jira_key,
                           r.version,
                           sr.run_id
                    FROM scenario_results sr
                    LEFT JOIN scenario_definitions sd ON sr.scenario_uid = sd.scenario_uid
                    LEFT JOIN runs r ON sr.run_id = r.id
                    WHERE sr.run_id = ? AND sr.scenario_uid = ?
                    LIMIT 1
                """, [run_id, scenario_uid]).fetchone()
            else:
                row = conn.execute("""
                    SELECT sr.scenario_uid, sr.name_at_run, sr.status, sr.duration_seconds,
                           sr.error_message, sd.current_name,
                           COALESCE(sr.doors_number_at_run, sd.doors_number) AS doors_number,
                           COALESCE(
                               sr.jira_key_at_run,
                               (SELECT jm.jira_key FROM jira_mappings jm WHERE jm.scenario_uid = sr.scenario_uid LIMIT 1),
                               (SELECT bm.jira_key FROM bug_mappings bm WHERE bm.doors_number = COALESCE(sr.doors_number_at_run, sd.doors_number) LIMIT 1)
                           ) AS jira_key,
                           r.version,
                           sr.run_id
                    FROM scenario_results sr
                    LEFT JOIN scenario_definitions sd ON sr.scenario_uid = sd.scenario_uid
                    LEFT JOIN runs r ON sr.run_id = r.id
                    WHERE sr.scenario_uid = ?
                    LIMIT 1
                """, [scenario_uid]).fetchone()
            if row:
                scenario_rows.append(row)

        scenarios_internal = []
        csv_rows = []
        manifest_doors_by_run_name = {}
        parsed_run_ids = {run_id for run_id, _, _ in parsed if run_id}
        if parsed_run_ids:
            for manifest in load_manifests():
                if manifest.runId not in parsed_run_ids:
                    continue
                for scenario in manifest.scenarios:
                    for tag in scenario.tags:
                        doors_match = re.search(r"@?(?:DOORS-\d+|ABS-\d+)", tag, re.IGNORECASE)
                        if doors_match:
                            manifest_doors_by_run_name.setdefault((manifest.runId, scenario.name), doors_match.group(0).lstrip("@"))
                            break
        passed = failed = skipped = 0
        for row in scenario_rows:
            status = row[2] or "UNKNOWN"
            if status == "PASSED":
                passed += 1
            elif status in {"FAILED", "BROKEN"}:
                failed += 1
            else:
                skipped += 1
            scenarios_internal.append({
                "id": row[0],
                "name": row[5] or row[1] or row[0],
                "status": status.lower(),
                "duration": f"PT{row[3]:.3f}S" if row[3] else "PT0S",
            })
            csv_rows.append({
                "doors_id": row[6] or manifest_doors_by_run_name.get((row[9], row[1]), ""),
                "name": row[5] or row[1] or row[0],
                "status": status,
                "jira_key": row[7] or "",
                "version": row[8] or "vX.X",
            })

        internal_report = {
            "totalScenarios": len(scenario_rows),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "scenarios": scenarios_internal,
            "generated_timestamp": datetime.now(timezone.utc),
        }

        from models import PublicReportSnapshot
        snapshot = PublicReportSnapshot.from_internal(internal_report)
        snapshot_payload = snapshot.model_dump(mode="json")
        snapshot_payload["_csv_export_rows"] = csv_rows
        snapshot_json = json.dumps(snapshot_payload, ensure_ascii=False)

        share_id = str(uuid4())
        conn.execute("""
            INSERT INTO public_snapshots (share_id, created_at, snapshot_data, status)
            VALUES (?, current_timestamp, ?, 'active')
        """, [share_id, snapshot_json])

        return {
            "share_id": share_id,
            "url": f"/public/reports/{share_id}",
        }
    finally:
        conn.close()


@app.get("/api/public/reports/{share_id}")
async def get_public_snapshot(share_id: str):
    """Return sanitized snapshot JSON (anonymous access)."""
    conn = get_connection(read_only=True)
    try:
        row = conn.execute(
            "SELECT snapshot_data FROM public_snapshots WHERE share_id = ? AND status = 'active'",
            [share_id],
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        import json as _json
        snapshot = _json.loads(row[0])
        snapshot.pop("_csv_export_rows", None)
        return snapshot
    finally:
        conn.close()


@app.get("/public/reports", response_class=HTMLResponse)
async def list_public_reports():
    conn = get_connection(read_only=True)
    try:
        rows = conn.execute(
            "SELECT share_id, created_at, snapshot_data FROM public_snapshots WHERE status = 'active' ORDER BY created_at ASC"
        ).fetchall()

        reports = []
        trend_labels = []
        trend_passed = []
        trend_failed = []
        trend_skipped = []
        total_passed = 0
        total_failed = 0
        total_skipped = 0
        total_scenarios = 0
        total_duration = 0.0

        for row in rows:
            try:
                snapshot = json.loads(row[2])
                summary = snapshot.get("run_summary", {})
                passed = summary.get("passed", 0) or 0
                failed = summary.get("failed", 0) or 0
                skipped = summary.get("skipped", 0) or 0
                scenarios = summary.get("total_scenarios", 0) or 0
                total_passed += passed
                total_failed += failed
                total_skipped += skipped
                total_scenarios += scenarios
                total_duration += float(snapshot.get("avg_duration", 0) or 0)

                dt = row[1]
                if hasattr(dt, "strftime"):
                    label = dt.strftime("%m-%d")
                else:
                    label = str(dt)[:10]

                trend_labels.append(label)
                trend_passed.append(passed)
                trend_failed.append(failed)
                trend_skipped.append(skipped)

                success_rate = round((passed / scenarios * 100), 1) if scenarios > 0 else 0
                reports.append({
                    "share_id": row[0],
                    "created_at": str(row[1])[:16] if row[1] else "",
                    "total_scenarios": scenarios,
                    "passed": passed,
                    "failed": failed,
                    "skipped": skipped,
                    "success_rate": success_rate,
                })
            except Exception:
                continue

        reports.reverse()
        trend_labels.reverse()
        trend_passed.reverse()
        trend_failed.reverse()
        trend_skipped.reverse()

        total_all = total_passed + total_failed + total_skipped
        success_rate = round((total_passed / total_all * 100), 1) if total_all > 0 else 0
        avg_duration = round((total_duration / len(rows)), 1) if rows else 0

        env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
        tpl = env.get_template("public_reports.html")
        html = tpl.render(
            reports=reports,
            success_rate=success_rate,
            total_scenarios=total_scenarios,
            avg_duration=avg_duration,
            total_passed=total_passed,
            total_failed=total_failed,
            total_skipped=total_skipped,
            trend_labels=trend_labels,
            trend_passed=trend_passed,
            trend_failed=trend_failed,
            trend_skipped=trend_skipped,
        )
        return HTMLResponse(content=html)
    finally:
        conn.close()


@app.get("/api/csv/export")
def export_csv(run_id: str, _: TokenData = Depends(verify_token_page)):
    conn = get_connection(read_only=True)
    try:
        rows = conn.execute(
            """
            SELECT
                COALESCE(sr.doors_number_at_run, sd.doors_number, '') AS doors_id,
                sr.status,
                COALESCE(
                    sr.jira_key_at_run,
                    (SELECT jm.jira_key FROM jira_mappings jm WHERE jm.scenario_uid = sr.scenario_uid LIMIT 1),
                    (SELECT bm.jira_key FROM bug_mappings bm WHERE bm.doors_number = COALESCE(sr.doors_number_at_run, sd.doors_number) LIMIT 1),
                    ''
                ) AS jira_key,
                COALESCE(r.version, 'vX.X') AS version,
                sr.name_at_run
            FROM scenario_results sr
            LEFT JOIN scenario_definitions sd ON sr.scenario_uid = sd.scenario_uid
            LEFT JOIN runs r ON sr.run_id = r.id
            WHERE sr.run_id = ?
            ORDER BY doors_id, sr.name_at_run
            """,
            [run_id],
        ).fetchall()

        if not rows:
            raise HTTPException(status_code=404, detail="No scenarios found for this run")

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Senaryo", "Durum", "Açıklama"])
        manifest_doors_by_name = {}
        for manifest in load_manifests():
            if manifest.runId != run_id:
                continue
            for scenario in manifest.scenarios:
                for tag in scenario.tags:
                    doors_match = re.search(r"@?(?:DOORS-\d+|ABS-\d+)", tag, re.IGNORECASE)
                    if doors_match:
                        manifest_doors_by_name.setdefault(scenario.name, doors_match.group(0).lstrip("@"))
                        break
            break

        for r in rows:
            doors_id, status, jira_key, version, name = r
            doors_id = doors_id or manifest_doors_by_name.get(name, "")
            if status == "PASSED":
                result_status = "Yapildi - Hata Yok"
                explanation = f"{version} sürümünde test otomasyon ile doğrulanmıştır."
            elif status in {"FAILED", "BROKEN"}:
                result_status = "Yapildi - Hata Var"
                explanation = jira_key or ""
            else:
                result_status = "Yapilmadi"
                explanation = "Test kapsamına alınmadığı için yapılmadı"
            writer.writerow([doors_id or "", result_status, explanation])

        content = "\ufeff" + output.getvalue()
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=doors_export_{run_id}.csv"},
        )
    finally:
        conn.close()


@app.get("/api/csv/share/{share_id}", dependencies=[Depends(verify_token)])
def export_csv_share(share_id: str):
    conn = get_connection(read_only=True)
    try:
        row = conn.execute(
            "SELECT snapshot_data FROM public_snapshots WHERE share_id = ? AND status = 'active'",
            [share_id],
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Snapshot not found")

        snapshot = json.loads(row[0])
        csv_export_rows = snapshot.get("_csv_export_rows") or snapshot.get("scenario_list", [])
        if not csv_export_rows:
            raise HTTPException(status_code=404, detail="No scenarios in snapshot")

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Senaryo", "Durum", "Açıklama"])
        for s in csv_export_rows:
            raw_status = (s.get("status") or "").upper()
            doors_id = s.get("doors_id") or ""
            version = s.get("version") or "vX.X"
            jira_key = s.get("jira_key") or ""

            if raw_status == "PASSED":
                result_status = "Yapildi - Hata Yok"
                explanation = f"{version} sürümünde test otomasyon ile doğrulanmıştır."
            elif raw_status in {"FAILED", "BROKEN"}:
                result_status = "Yapildi - Hata Var"
                explanation = jira_key
            else:
                result_status = "Yapilmadi"
                explanation = "Test kapsamına alınmadığı için yapılmadı"
            writer.writerow([doors_id, result_status, explanation])

        content = "\ufeff" + output.getvalue()
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=report_{share_id[:8]}.csv"},
        )
    finally:
        conn.close()


@app.get("/public/reports/{share_id}", response_class=HTMLResponse)
async def render_public_report(share_id: str):
    """Render public HTML report (anonymous access).

    Only exposes PublicReportSnapshot allowlisted fields:
    title, generated_timestamp, total_passed/failed/skipped,
    scenario_list (name + status only).
    No internal identifiers, no Jira/DOORS, no paths, no logs.
    """
    conn = get_connection(read_only=True)
    try:
        row = conn.execute(
            "SELECT snapshot_data FROM public_snapshots WHERE share_id = ? AND status = 'active'",
            [share_id],
        ).fetchone()
        if not row:
            env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
            tpl = env.get_template("public_404.html")
            return HTMLResponse(content=tpl.render(), status_code=404)
        import json as _json
        snapshot = _json.loads(row[0])

        scenario_list = [
            {"name": s.get("name", ""), "status": s.get("status", "unknown")}
            for s in snapshot.get("scenario_list", [])
        ]

        env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
        tpl = env.get_template("public_report.html")
        html = tpl.render(
            title=snapshot.get("run_summary", {}).get("total_scenarios", 0),
            generated_timestamp=snapshot.get("generated_timestamp", ""),
            total_passed=snapshot.get("total_passed", 0),
            total_failed=snapshot.get("total_failed", 0),
            total_skipped=snapshot.get("total_skipped", 0),
            total_scenarios=snapshot.get("run_summary", {}).get("total_scenarios", 0),
            scenario_list=scenario_list,
        )
        return HTMLResponse(content=html)
    finally:
        conn.close()


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
                            error_message, feature_file_at_run, doors_number_at_run)
                           VALUES (?, ?, ?, ?, ?, ?, '', ?)""",
                        [run_id, uid, s.name, s.status.upper(), 0.0, None,
                         s.doorsAbsNumber or None],
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


@app.delete("/api/admin/runs/{run_id}", dependencies=[Depends(verify_token)])
def delete_run(run_id: str):
    with get_connection(read_only=False) as conn:
        init_schema(conn)
        conn.execute("DELETE FROM scenario_results WHERE run_id = ?", [run_id])
        conn.execute("DELETE FROM pipeline_status WHERE run_id = ?", [run_id])
        conn.execute("DELETE FROM runs WHERE id = ?", [run_id])
        conn.commit()
    manifest_path = MANIFESTS_DIR / f"{run_id}.json"
    if manifest_path.exists():
        manifest_path.unlink()
    return {"deleted": run_id}


@app.delete("/api/admin/runs", dependencies=[Depends(verify_token)])
def delete_all_runs():
    with get_connection(read_only=False) as conn:
        init_schema(conn)
        conn.execute("DELETE FROM scenario_results")
        conn.execute("DELETE FROM pipeline_status")
        conn.execute("DELETE FROM runs")
        conn.commit()
    if MANIFESTS_DIR.exists():
        for f in MANIFESTS_DIR.glob("*.json"):
            f.unlink()
    return {"deleted": "all"}


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
async def report_merge_page(request: Request, _: TokenData = Depends(verify_token_page)):
    template = jinja_env.get_template("report-merge.html")
    return HTMLResponse(content=template.render())


@app.get("/reports/{run_id}", response_class=HTMLResponse)
def run_detail(run_id: str, request: Request, _: TokenData = Depends(verify_token_page)):
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
def scenario_detail(run_id: str, scenario_id: str, _: TokenData = Depends(verify_token_page)):
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
def triage_page(run_id: str, request: Request, _: TokenData = Depends(verify_token_page)):
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
    failures = [s for s in manifest.scenarios if s.status in ("failed", "broken")]

    template = jinja_env.get_template("triage.html")
    html = template.render(
        run_id=run_id,
        manifest=manifest.model_dump(),
        failures=[s.model_dump() for s in failures],
        jira_base_url=os.getenv("JIRA_BASE_URL", ""),
    )
    return HTMLResponse(content=html)


@app.get("/reports/{artifact_path:path}")
def protected_report_artifact(artifact_path: str, _: TokenData = Depends(verify_token_page)):
    """Serve report attachments only to authenticated engineer sessions.

    Raw report artifacts can contain screenshots, videos, logs, and filesystem-derived
    manifest paths. Keep the URL shape used by internal templates, but require a
    bearer token and resolve paths under MANIFESTS_DIR to prevent public/static leaks.
    """
    candidate = (MANIFESTS_DIR / artifact_path).resolve()
    reports_root = MANIFESTS_DIR.resolve()
    try:
        candidate.relative_to(reports_root)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    if not candidate.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    return FileResponse(candidate)


class JiraResponse(BaseModel):
    jiraKey: str
    jiraUrl: Optional[str] = None


@app.post("/api/v1/runs/{run_id}/scenarios/{scenario_id}/jira", response_model=JiraResponse, status_code=201, dependencies=[Depends(verify_token)])
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


@app.get("/api/v1/bugs", dependencies=[Depends(verify_token)])
def list_bugs():
    return tracker.get_all()


@app.get("/api/v1/bugs/{doors_number}", dependencies=[Depends(verify_token)])
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
    if os.getenv("DRY_RUN", "false").lower() not in {"1", "true", "yes", "on"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Fake Jira bug creation is available only when DRY_RUN is enabled.",
        )

    existing = tracker.get(doors_number)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=existing,
        )
    issue = JiraClient(dry_run=True).create_issue(
        req.scenarioName,
        f"Dry-run bug mapping for run {req.runId} and DOORS item {doors_number}.",
        doors_number,
    )
    jira_key = issue["key"]
    tracker.register(doors_number, jira_key, req.scenarioName, req.runId)
    return BugCreateResponse(jiraKey=jira_key, doorsNumber=doors_number)


class DoorsRunRequest(BaseModel):
    script: str


class TriageScenarioState(BaseModel):
    scenario_uid: str
    scenario_name: str
    status: str
    error_message: Optional[str] = None
    doors_number: Optional[str] = None
    jira_keys: List[str] = []
    triage_decision: Optional[str] = None
    triage_reason: Optional[str] = None
    triage_actor: Optional[str] = None
    triage_timestamp: Optional[str] = None
    is_flaky: bool = False
    retry_attempt: int = 1


class TriageStateResponse(BaseModel):
    run_id: str
    total_failed: int
    scenarios: List[TriageScenarioState]


class OverrideRequest(BaseModel):
    decision: str
    reason: str


class LinkJiraRequest(BaseModel):
    jira_key: str


@app.post("/api/doors/run", dependencies=[Depends(verify_token)])
async def doors_run(req: DoorsRunRequest):
    if not is_doors_available():
        return {"status": "unavailable", "message": "DOORS not installed"}
    code, out, err = run_doors_dxl(req.script)
    return {"status": "success" if code == 0 else "failed", "stdout": out, "stderr": err}


@app.post("/api/email/send", dependencies=[Depends(verify_token)])
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


@app.post("/api/doors/share/{share_id}", dependencies=[Depends(verify_token)])
async def doors_share_export(share_id: str):
    """Engineer-only: DOORS export for a public share snapshot."""
    conn = get_connection(read_only=True)
    try:
        row = conn.execute(
            "SELECT snapshot_data FROM public_snapshots WHERE share_id = ? AND status = 'active'",
            [share_id],
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        import json as _json
        snapshot = _json.loads(row[0])

        # Build DXL script content from snapshot data
        scenario_list = snapshot.get("scenario_list", [])
        scenario_names = [s.get("name", "") for s in scenario_list if s.get("name")]
        scenario_block = "\n".join(f'  "{name}"' for name in scenario_names if name)

        dxl_script = f"""// DOORS export for public share {share_id}
// Scenarios: {len(scenario_list)}
string[] scenarios = {{{scenario_block}
}};
print("DOORS share export: " + str(scenario_list.length()) + " scenarios\\n");
"""
        if not is_doors_available():
            conn.close()
            return {"status": "unavailable", "message": "DOORS not installed"}
        code, out, err = run_doors_dxl(dxl_script)
        conn.close()
        return {"status": "success" if code == 0 else "failed", "stdout": out, "stderr": err}
    except HTTPException:
        raise
    except Exception:
        conn.close()
        raise HTTPException(status_code=500, detail="DOORS export failed")


@app.post("/api/email/share/{share_id}", dependencies=[Depends(verify_token)])
async def email_share_send(share_id: str, to: str):
    """Engineer-only: send email with public share link /public/reports/{share_id}."""
    conn = get_connection(read_only=True)
    try:
        row = conn.execute(
            "SELECT snapshot_data FROM public_snapshots WHERE share_id = ? AND status = 'active'",
            [share_id],
        ).fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Snapshot not found")
        import json as _json
        snapshot = _json.loads(row[0])
        run_summary = snapshot.get("run_summary", {})
        context = {
            "total": run_summary.get("total_scenarios", 0),
            "passed": run_summary.get("passed", 0),
            "failed": run_summary.get("failed", 0),
            "skipped": run_summary.get("skipped", 0),
            "started_at": snapshot.get("generated_timestamp", ""),
            "dashboard_url": f"/public/reports/{share_id}",
        }
        send_email(to, f"Test Raporu - {share_id}", "test_report.html", context)
        return {"sent": True}
    except HTTPException:
        conn.close()
        raise
    except Exception as e:
        conn.close()
        return {"sent": False, "error": str(e)}


@app.get("/api/triage/{run_id}", response_model=TriageStateResponse, dependencies=[Depends(verify_token)])
def get_triage_state(run_id: str):
    conn = get_connection(read_only=True)
    try:
        rows = conn.execute("""
            SELECT
                sr.scenario_uid,
                COALESCE(sd.current_name, sr.name_at_run) as scenario_name,
                sr.status,
                sr.error_message,
                COALESCE(sr.doors_number_at_run, sd.doors_number) as doors_number,
                (SELECT string_agg(jm.jira_key, ',') FROM jira_mappings jm WHERE jm.scenario_uid = sr.scenario_uid) as jira_keys,
                td.decision as triage_decision,
                td.reason as triage_reason,
                td.actor as triage_actor,
                td.timestamp as triage_timestamp,
                sr.retry_attempt
            FROM scenario_results sr
            LEFT JOIN scenario_definitions sd ON sr.scenario_uid = sd.scenario_uid
            LEFT JOIN triage_decisions td ON sr.scenario_uid = td.scenario_uid
            WHERE sr.run_id = ? AND sr.status IN ('FAILED', 'BROKEN')
            ORDER BY sr.id
        """, [run_id]).fetchall()
        if not rows:
            run_exists = conn.execute("SELECT 1 FROM runs WHERE id = ?", [run_id]).fetchone()
            if not run_exists:
                raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

        # Detect flaky: scenario has multiple FAILED attempts in this run
        flaky_uids = set()
        uid_counts: dict[str, int] = {}
        for row in rows:
            uid = row[0] or ""
            uid_counts[uid] = uid_counts.get(uid, 0) + 1
        for uid, count in uid_counts.items():
            if count > 1:
                flaky_uids.add(uid)

        scenarios = [
            TriageScenarioState(
                scenario_uid=row[0] or "",
                scenario_name=row[1] or "",
                status=row[2] or "UNKNOWN",
                error_message=row[3],
                doors_number=row[4],
                jira_keys=[k for k in (row[5] or "").split(",") if k],
                triage_decision=row[6],
                triage_reason=row[7],
                triage_actor=row[8],
                triage_timestamp=str(row[9]) if row[9] else None,
                is_flaky=(row[0] or "") in flaky_uids,
                retry_attempt=row[10] if row[10] else 1,
            )
            for row in rows
        ]
        return TriageStateResponse(run_id=run_id, total_failed=len(scenarios), scenarios=scenarios)
    finally:
        conn.close()


@app.post("/api/triage/{run_id}/auto-match-jira", dependencies=[Depends(verify_token)])
def auto_match_jira(run_id: str) -> dict:
    """For each failed scenario with a DOORS number, search Jira for existing issues and auto-link."""
    if not jira_client.is_configured():
        return {"matched": 0, "details": [], "skipped_reason": "Jira not configured"}

    conn = get_connection(read_only=False)
    try:
        init_schema(conn)
        rows = conn.execute("""
            SELECT sr.scenario_uid, sr.name_at_run,
                   COALESCE(sr.doors_number_at_run, sd.doors_number) AS doors_number
            FROM scenario_results sr
            LEFT JOIN scenario_definitions sd ON sr.scenario_uid = sd.scenario_uid
            WHERE sr.run_id = ? AND sr.status IN ('FAILED', 'BROKEN')
              AND COALESCE(sr.doors_number_at_run, sd.doors_number) IS NOT NULL
              AND COALESCE(sr.doors_number_at_run, sd.doors_number) != ''
        """, [run_id]).fetchall()

        INACTIVE_STATUSES = {"done", "closed", "resolved", "cancelled", "wont fix", "won't fix", "duplicate", "rejected"}

        matched = 0
        details = []
        for scenario_uid, scenario_name, doors_number in rows:
            # Skip if manually triaged by a human
            existing_decision = conn.execute(
                "SELECT actor FROM triage_decisions WHERE scenario_uid = ? LIMIT 1",
                [scenario_uid],
            ).fetchone()
            if existing_decision and existing_decision[0] != "auto-match":
                continue

            try:
                issues = jira_client.search_by_doors_number(doors_number)
            except Exception:
                continue

            active_issues = [i for i in issues if i.get("status", "").lower() not in INACTIVE_STATUSES]
            if not active_issues:
                continue

            linked_keys = []
            for issue in active_issues:
                jira_key = issue["key"]
                conn.execute(
                    "INSERT OR IGNORE INTO jira_mappings (scenario_uid, doors_id, jira_key, created_at) VALUES (?, ?, ?, ?)",
                    [scenario_uid, doors_number, jira_key, datetime.now()],
                )
                linked_keys.append(jira_key)

            conn.execute(
                """INSERT OR REPLACE INTO triage_decisions
                   (scenario_uid, decision, reason, actor, timestamp)
                   VALUES (?, 'jira_linked', ?, 'auto-match', ?)""",
                [scenario_uid, f"Auto-matched by DOORS number {doors_number}: {', '.join(linked_keys)}", datetime.now()],
            )
            matched += 1
            details.append({
                "scenario_uid": scenario_uid,
                "scenario_name": scenario_name,
                "doors_number": doors_number,
                "jira_keys": linked_keys,
                "jira_statuses": [i.get("status", "") for i in active_issues],
            })

        return {"matched": matched, "details": details}
    finally:
        conn.close()


@app.post("/api/triage/{run_id}/scenarios/{scenario_id}/jira", response_model=JiraResponse, status_code=201, dependencies=[Depends(verify_token)])
def create_triage_jira(run_id: str, scenario_id: str, _: TokenData = Depends(verify_token)):
    conn = get_connection(read_only=False)
    try:
        init_schema(conn)
        row = conn.execute("""
            SELECT sr.scenario_uid, sr.name_at_run, sr.error_message, sr.doors_number_at_run,
                   sd.current_name, sd.current_feature_file, sd.current_feature_line,
                   sr.screenshot_path, sr.video_path
            FROM scenario_results sr
            LEFT JOIN scenario_definitions sd ON sr.scenario_uid = sd.scenario_uid
            WHERE sr.run_id = ? AND sr.scenario_uid = ?
        """, [run_id, scenario_id]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found in run '{run_id}'")

        scenario_uid, name_at_run, error_message, doors_number = row[0], row[1], row[2], row[3]
        scenario_name = row[4] or name_at_run
        screenshot_path = row[7]
        video_path = row[8]

        if not jira_client.is_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Jira integration not configured. Set JIRA_BASE_URL, JIRA_PAT, JIRA_PROJECT.",
            )

        summary = f"Automated test failed: {scenario_name}"
        description = (
            f"h2. Automated Test Failure\n\n"
            f"*Run ID:* {run_id}\n"
            f"*Scenario:* {scenario_name}\n"
            f"*DOORS Number:* {doors_number or 'N/A'}\n\n"
            f"h3. Error\n{{noformat}}\n{error_message or 'No error message'}\n{{noformat}}"
        )

        try:
            issue = jira_client.create_issue(summary, description, doors_number)
            key = issue["key"] if isinstance(issue, dict) else issue
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Jira error: {str(exc)}",
            )

        conn.execute("""
            INSERT OR IGNORE INTO jira_mappings (scenario_uid, doors_id, jira_key, created_at)
            VALUES (?, ?, ?, current_timestamp)
        """, [scenario_id, doors_number, key])

        now = datetime.now()
        conn.execute("""
            INSERT INTO triage_decisions (scenario_uid, run_id, decision, actor, timestamp)
            VALUES (?, ?, 'jira_created', 'engineer', ?)
            ON CONFLICT (scenario_uid) DO UPDATE SET
                decision = 'jira_created', actor = 'engineer', timestamp = ?
        """, [scenario_id, run_id, now, now])

        if doors_number:
            update_scenario_history_explanation(conn, doors_number, run_id, key)

        # Attach screenshot/video if available
        for fpath in [screenshot_path, video_path]:
            if fpath:
                full = (MANIFESTS_DIR / fpath).resolve()
                if full.exists() and str(full).startswith(str(MANIFESTS_DIR.resolve())):
                    try:
                        jira_client.attach_screenshot(key, str(full))
                    except Exception:
                        pass

        return JiraResponse(jiraKey=key, jiraUrl=jira_client.issue_url(key))
    finally:
        conn.close()


@app.post("/api/triage/{run_id}/scenarios/{scenario_id}/override", response_model=dict, status_code=200, dependencies=[Depends(verify_token)])
def override_scenario(run_id: str, scenario_id: str, req: OverrideRequest, token: TokenData = Depends(verify_token)):
    if not req.reason or not req.reason.strip():
        raise HTTPException(status_code=422, detail="Reason is required and cannot be empty")

    if req.decision not in ("accepted_pass", "accepted_skip"):
        raise HTTPException(
            status_code=422,
            detail="Decision must be 'accepted_pass' or 'accepted_skip'",
        )

    conn = get_connection(read_only=False)
    try:
        init_schema(conn)
        row = conn.execute("""
            SELECT scenario_uid, status FROM scenario_results
            WHERE run_id = ? AND scenario_uid = ?
        """, [run_id, scenario_id]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found in run '{run_id}'")

        previous_status = row[1]
        actor = token.username
        now = datetime.now()

        conn.execute("""
            INSERT INTO override_audit (scenario_uid, previous_status, new_decision, reason, actor, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [scenario_id, previous_status, req.decision, req.reason.strip(), actor, now])

        conn.execute("""
            INSERT INTO triage_decisions (scenario_uid, run_id, decision, actor, reason, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (scenario_uid) DO UPDATE SET
                decision = ?, actor = ?, reason = ?, timestamp = ?
        """, [scenario_id, run_id, req.decision, actor, req.reason.strip(), now,
              req.decision, actor, req.reason.strip(), now])

        return {"success": True, "scenario_uid": scenario_id, "decision": req.decision}
    finally:
        conn.close()


@app.post("/api/triage/{run_id}/scenarios/{scenario_id}/link-jira", response_model=JiraResponse, status_code=200, dependencies=[Depends(verify_token)])
def link_jira_issue(run_id: str, scenario_id: str, req: LinkJiraRequest, _: TokenData = Depends(verify_token)):
    jira_key = req.jira_key.strip()
    if not jira_key:
        raise HTTPException(status_code=422, detail="jira_key is required")

    conn = get_connection(read_only=False)
    try:
        init_schema(conn)
        row = conn.execute("""
            SELECT sr.scenario_uid, sr.doors_number_at_run
            FROM scenario_results sr
            WHERE sr.run_id = ? AND sr.scenario_uid = ?
        """, [run_id, scenario_id]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found in run '{run_id}'")

        doors_number = row[1]

        existing = conn.execute("""
            SELECT 1 FROM jira_mappings WHERE scenario_uid = ? AND jira_key = ?
        """, [scenario_id, jira_key]).fetchone()
        if existing:
            return JiraResponse(jiraKey=jira_key, jiraUrl=jira_client.issue_url(jira_key))

        conn.execute("""
            INSERT INTO jira_mappings (scenario_uid, doors_id, jira_key, created_at)
            VALUES (?, ?, ?, ?)
        """, [scenario_id, doors_number, jira_key, datetime.now()])

        conn.execute("""
            INSERT INTO triage_decisions (scenario_uid, run_id, decision, actor, timestamp)
            VALUES (?, ?, 'jira_linked', 'engineer', ?)
            ON CONFLICT (scenario_uid) DO UPDATE SET
                decision = 'jira_linked', actor = 'engineer', timestamp = ?
        """, [scenario_id, run_id, datetime.now(), datetime.now()])

        if doors_number:
            update_scenario_history_explanation(conn, doors_number, run_id, jira_key)

        return JiraResponse(jiraKey=jira_key, jiraUrl=jira_client.issue_url(jira_key))
    finally:
        conn.close()


MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
