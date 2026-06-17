import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
import asyncio
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
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
from maven import maven_executable
from services.identifiers import extract_doors_id
from services.csv_export import doors_csv_row, doors_csv_document
from services.jira_helper import build_jira_description
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
# JAVA_PROJECT_ROOT: Maven parent pom.xml directory (defaults to repo root)
PROJECT_ROOT = Path(os.getenv("JAVA_PROJECT_ROOT", str(Path(__file__).parent.parent)))
# MAVEN_MODULE: -pl argument passed to Maven (defaults to "test-core")
MAVEN_MODULE = os.getenv("MAVEN_MODULE", "test-core")

# Run lifecycle (queue + watchdog): job-level concurrency limit and timeouts
TEST_MAX_CONCURRENCY = int(os.getenv("TEST_MAX_CONCURRENCY", "1"))
RUN_HARD_TIMEOUT = int(os.getenv("RUN_HARD_TIMEOUT", "3600"))
RUN_STALL_TIMEOUT = int(os.getenv("RUN_STALL_TIMEOUT", "900"))

_aliases_lock = threading.Lock()

running_tests: dict[str, object] = {}
test_tasks: set[asyncio.Task] = set()
tests_lock = threading.Lock()


def _persist_worker(run_id: str, **fields) -> None:
    """Best-effort UPDATE of worker_runs lifecycle columns for a run.

    Only a fixed allow-list of columns is accepted, so the dynamically-built
    SQL is safe. Used to record pid, heartbeat (last_output_at) and exit_code.
    """
    allowed = {"pid", "last_output_at", "exit_code"}
    cols = [c for c in fields if c in allowed]
    if not cols:
        return
    assignments = ", ".join(f"{c} = ?" for c in cols)
    try:
        with get_connection(read_only=False) as conn:
            conn.execute(
                f"UPDATE worker_runs SET {assignments} WHERE run_id = ?",
                [*(fields[c] for c in cols), run_id],
            )
            conn.commit()
    except Exception:
        pass


def _terminate_proc(proc) -> None:
    """Terminate a run's whole process group (POSIX), falling back to the direct
    child. Shared by cancellation and the stall/hard-timeout watchdog so no
    orphan java/chromedriver is left behind."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, OSError):
        try:
            proc.kill()
        except Exception:
            pass


async def _broadcast_state(run_id: str, status: str, **extra) -> None:
    """Emit a lifecycle state frame for a run. ws_manager mirrors per-run
    messages to the 'live' channel, so the admin/live panel sees transitions."""
    try:
        await ws_manager.broadcast(run_id, {"type": "state", "run_id": run_id, "status": status, **extra})
    except Exception:
        pass


def _abort_reason(elapsed: float, idle: float) -> str | None:
    """Return why a run should be aborted, or None. ``elapsed`` is total wall
    time; ``idle`` is seconds since last output. A 0/false timeout disables it."""
    if RUN_HARD_TIMEOUT and elapsed > RUN_HARD_TIMEOUT:
        return "hard timeout"
    if RUN_STALL_TIMEOUT and idle > RUN_STALL_TIMEOUT:
        return "stalled (no output)"
    return None


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


def _maybe_kill_stale(pid) -> None:
    """Best-effort, PID-reuse-guarded kill of a leftover run process (POSIX only).

    Only signals the process group if the pid still maps to what looks like our
    Maven/test-core run, so a recycled pid belonging to something else is left
    alone. On non-Linux (no /proc) we skip the kill and only mark interrupted.
    """
    if not pid:
        return
    try:
        cmdline = Path(f"/proc/{int(pid)}/cmdline").read_bytes().decode(errors="replace")
    except (OSError, ValueError):
        return
    if not any(m in cmdline for m in ("maven", "surefire", "test-core", MAVEN_MODULE)):
        return
    try:
        os.killpg(os.getpgid(int(pid)), signal.SIGTERM)
    except (ProcessLookupError, OSError):
        pass


def _recover_orphans() -> int:
    """Reconcile runs left 'running' by a previous (now-dead) process.

    A freshly started process owns no in-flight runs, so any 'running' row is an
    orphan: kill its leftover child if still alive, then mark run + job
    'interrupted'. Returns the number of runs interrupted.
    """
    with get_connection(read_only=False) as conn:
        init_schema(conn)
        stale = conn.execute(
            "SELECT run_id, pid FROM worker_runs WHERE status = 'running'"
        ).fetchall()
        for _run_id, pid in stale:
            _maybe_kill_stale(pid)
        if stale:
            now = datetime.now()
            conn.execute(
                "UPDATE worker_runs SET status = 'interrupted', ended_at = ? WHERE status = 'running'",
                [now],
            )
            conn.execute(
                "UPDATE jobs SET status = 'interrupted', ended_at = ? WHERE status = 'running'",
                [now],
            )
            conn.commit()
        return len(stale)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("RUN_RECOVERY_ON_STARTUP", "1") == "1":
        try:
            recovered = _recover_orphans()
            if recovered:
                print(f"[startup] marked {recovered} orphaned run(s) as interrupted")
            _dispatch_queued()
        except Exception as exc:  # never block startup on recovery
            print(f"[startup] orphan recovery skipped: {exc}")
    yield


app = FastAPI(title="Test Reports API", version="1.0.0", lifespan=lifespan)
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


def _test_command(options: TestRunOptions, output_dir: str | None = None) -> list[str]:
    cmd = [
        maven_executable(),
        "-pl", MAVEN_MODULE,
        "test",
        f"-Dcucumber.filter.tags={options.tags}",
        f"-Dbrowser={options.browser}",
    ]
    if options.retry_count:
        cmd.append(f"-Dretry.count={options.retry_count}")
    # Shard workers restrict execution to their assigned feature files.
    if getattr(options, "features", None):
        cmd.append(f"-Dcucumber.features={options.features}")
    if output_dir:
        cmd.append(f"-Dallure.results.directory={output_dir}")
    return cmd


_SCENARIO_LINE_RE = re.compile(r"^\s*Scenario(?: Outline)?:\s*(.+?)\s+#\s+(\S+?):(\d+)\s*$")


def _discover_scenarios(tags: str = "@smoke") -> list[dict]:
    """Discover scenarios + their feature files for a tag filter, using Cucumber
    dry-run (parses features, runs no steps/hooks → no browser needed).
    Returns [{name, feature, line}]."""
    cmd = [
        maven_executable(), "-pl", MAVEN_MODULE, "test",
        f"-Dcucumber.filter.tags={tags}", "-Dcucumber.execution.dry-run=true",
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=str(PROJECT_ROOT), env=_test_env(),
            capture_output=True, text=True, timeout=300,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise RuntimeError(f"scenario discovery failed: {exc}") from exc
    scenarios = []
    for line in proc.stdout.splitlines():
        m = _SCENARIO_LINE_RE.match(line)
        if m:
            scenarios.append({"name": m.group(1).strip(), "feature": m.group(2), "line": int(m.group(3))})
    return scenarios


def _shard_features(features: list[str], n: int) -> list[list[str]]:
    """Round-robin split unique feature files into n balanced shards
    (order-stable; empty shards dropped). Never returns more shards than files."""
    uniq = list(dict.fromkeys(features))
    if not uniq:
        return []
    n = max(1, min(n, len(uniq)))
    shards: list[list[str]] = [[] for _ in range(n)]
    for i, f in enumerate(uniq):
        shards[i % n].append(f)
    return shards


def _test_env() -> dict[str, str]:
    env = os.environ.copy()
    env["DISPLAY"] = env.get("DISPLAY", ":0")
    maven_parent = Path(maven_executable()).parent
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


def _spawn_run(run_id: str, options: TestRunOptions, output_dir: str | None) -> None:
    """Create the background task that executes a single run.

    Isolated seam so the queue/recovery logic can be tested without launching
    a real Maven subprocess (tests monkeypatch this).
    """
    task = asyncio.create_task(execute_test_run(run_id, options, output_dir=output_dir))
    test_tasks.add(task)
    task.add_done_callback(lambda t: test_tasks.discard(t))
    task.add_done_callback(_log_task_exception)


def _worker_specs(options: TestRunOptions) -> list[tuple[str, str, str, str | None]]:
    """Resolve a run into a (tags, browser, environment, features) tuple per worker.

    - ``single``: ``parallel`` identical copies (features=None).
    - ``matrix``: one entry per worker spec (its own tags/browser/environment).
    - ``shard``: discover scenarios (dry-run), split their feature files into
      ``parallel`` shards; each worker runs one feature subset via -Dcucumber.features."""
    if options.mode == "matrix" and options.workers:
        return [
            (w.tags, w.browser or options.browser, w.environment or options.environment, None)
            for w in options.workers
        ]
    if options.mode == "shard":
        scenarios = _discover_scenarios(options.tags)
        shards = _shard_features([s["feature"] for s in scenarios], options.parallel)
        if not shards:
            return [(options.tags, options.browser, options.environment, None)]
        return [
            (options.tags, options.browser, options.environment, ",".join(shard))
            for shard in shards
        ]
    return [(options.tags, options.browser, options.environment, None) for _ in range(options.parallel)]


def _worker_options(tags, browser, environment, retry_count, version, features=None) -> TestRunOptions:
    """Build a single-worker TestRunOptions for executing or re-queuing one
    worker (per-worker tags/browser/environment/features + job-level retry/version)."""
    return TestRunOptions(
        tags=tags or "@smoke",
        browser=browser or "chrome",
        environment=environment or "staging",
        retry_count=retry_count or 0,
        version=version,
        parallel=1,
        features=features,
    )


def _dispatch_queued() -> list[str]:
    """Promote FIFO-queued jobs to running while capacity is available.

    Returns the job_ids that were started. Safe to call from any context with a
    running event loop (request handler, run completion, startup recovery).
    """
    started: list[str] = []
    with tests_lock:
        with get_connection(read_only=False) as conn:
            while True:
                running = conn.execute(
                    "SELECT COUNT(*) FROM jobs WHERE status = 'running'"
                ).fetchone()[0]
                if running >= TEST_MAX_CONCURRENCY:
                    break
                job = conn.execute(
                    "SELECT job_id, retry_count, version "
                    "FROM jobs WHERE status = 'queued' ORDER BY started_at, job_id LIMIT 1"
                ).fetchone()
                if not job:
                    break
                job_id, retry_count, version = job[0], job[1], job[2]
                now = datetime.now()
                conn.execute(
                    "UPDATE jobs SET status = 'running', started_at = ? WHERE job_id = ?",
                    [now, job_id],
                )
                conn.execute(
                    "UPDATE worker_runs SET status = 'running', started_at = ? WHERE job_id = ?",
                    [now, job_id],
                )
                worker_rows = conn.execute(
                    "SELECT run_id, output_dir, tags, browser, environment, features "
                    "FROM worker_runs WHERE job_id = ? ORDER BY shard",
                    [job_id],
                ).fetchall()
                conn.commit()
                for run_id, output_dir, wtags, wbrowser, wenv, wfeatures in worker_rows:
                    wopts = _worker_options(wtags, wbrowser, wenv, retry_count, version, wfeatures)
                    _spawn_run(run_id, wopts, output_dir)
                started.append(job_id)
    return started


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
        start_new_session=True,
    )
    with tests_lock:
        running_tests[run_id] = proc  # type: ignore[assignment]
    _persist_worker(run_id, pid=proc.pid, last_output_at=started_at)

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

    heartbeat = {"last": time.monotonic()}

    def beat() -> None:
        # Throttled liveness marker for stall detection (at most every 5s).
        loop_now = time.monotonic()
        if loop_now - heartbeat["last"] >= 5:
            heartbeat["last"] = loop_now
            _persist_worker(run_id, last_output_at=datetime.now())

    async def watchdog() -> None:
        # Abort a run that exceeds the hard timeout or stops emitting output.
        start = time.monotonic()
        interval = max(5, min(30, RUN_STALL_TIMEOUT or 30))
        while getattr(proc, "returncode", None) is None:
            await asyncio.sleep(interval)
            if getattr(proc, "returncode", None) is not None:
                return
            now_m = time.monotonic()
            reason = _abort_reason(now_m - start, now_m - heartbeat["last"])
            if reason:
                stats["error"] = reason
                print(f"[WATCHDOG] aborting run {run_id}: {reason}")
                _terminate_proc(proc)
                return

    async def consume_stream(stream: asyncio.StreamReader | None) -> None:
        if stream is None:
            return
        async for line in stream:
            decoded = line.decode(errors="replace").strip()
            if not decoded:
                continue
            stats["output"].append(decoded)
            beat()

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
        wd = asyncio.create_task(watchdog())
        try:
            await asyncio.gather(consume_stream(proc.stdout), consume_stream(proc.stderr))
            await proc.wait()
        finally:
            wd.cancel()
        saved = _save_results_to_duckdb(run_id, options, started_at, allure_dir=output_dir)
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
    exit_code = getattr(proc, "returncode", None)
    with get_connection(read_only=False) as conn:
        conn.execute(
            "UPDATE worker_runs SET status = ?, ended_at = ?, exit_code = ? WHERE run_id = ? AND status != 'cancelled'",
            [final_status, now, exit_code, run_id],
        )
        status_row = conn.execute(
            "SELECT status FROM worker_runs WHERE run_id = ?", [run_id]
        ).fetchone()
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
                    "UPDATE jobs SET status = ?, ended_at = ? WHERE job_id = ? AND status != 'cancelled'",
                    [final_status, now, job_row[0]],
                )
        conn.commit()

    # Emit the run's authoritative final status (cancelled survives the guard).
    await _broadcast_state(run_id, status_row[0] if status_row else final_status, exit_code=exit_code)

    # A run finished — promote the next queued job now that capacity may be free.
    try:
        _dispatch_queued()
    except Exception:
        pass


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
            found_doors = extract_doors_id(tag_str)
            if found_doors:
                doors_id = found_doors
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

    # Parse steps (Cucumber BDD steps from Allure result)
    raw_steps = data.get("steps") or []
    steps = []
    for st in raw_steps:
        step_error = ((st.get("statusDetails") or {}).get("message") or "")[:300]
        steps.append({
            "name": st.get("name") or "",
            "status": (st.get("status") or "unknown").lower(),
            "errorMessage": step_error or None,
        })

    # Collect attachments from the test and its steps (screenshots, videos).
    attachments: list[dict] = []

    def _collect_atts(node):
        for a in (node.get("attachments") or []):
            if isinstance(a, dict) and a.get("source"):
                attachments.append({
                    "name": a.get("name") or a["source"],
                    "type": a.get("type") or "",
                    "source": a["source"],
                })
        for st in (node.get("steps") or []):
            _collect_atts(st)

    _collect_atts(data)

    def _first_source(*, image: bool) -> str | None:
        for a in attachments:
            t, src = a["type"].lower(), a["source"].lower()
            if image and ("image" in t or src.endswith((".png", ".jpg", ".jpeg"))):
                return a["source"]
            if not image and ("video" in t or src.endswith(".mp4")):
                return a["source"]
        return None

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
        "attachments": attachments,
        "screenshot_source": _first_source(image=True),
        "video_source": _first_source(image=False),
        "start_ts_ms": start_ts or 0,
    }


def _copy_run_attachment(allure_dir: Path, run_id: str, source: str | None) -> str | None:
    """Copy an Allure attachment into MANIFESTS_DIR/{run_id}/ and return its path
    relative to MANIFESTS_DIR (servable via /reports/{path}). None if missing."""
    if not source:
        return None
    src = allure_dir / source
    if not src.exists():
        return None
    dest_dir = MANIFESTS_DIR / run_id
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest_dir / source)
    except OSError:
        return None
    return f"{run_id}/{source}"


def _persist_run(run_id, options, all_scenarios, passed, failed, skipped, effective_version, started_at, finished_at) -> None:
    """Write the run and its scenarios (definitions, results, history) to DuckDB
    and emit the manifest JSON. Extracted from _save_results_to_duckdb."""
    conn = get_connection(read_only=False)
    try:
        init_schema(conn)
        conn.execute("DELETE FROM scenario_results WHERE run_id = ?", [run_id])
        run_values = [effective_version, options.environment, started_at or finished_at, finished_at, len(all_scenarios), passed, failed, skipped, options.visibility, run_id]
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
                (run_id, scenario_uid, name_at_run, status, duration_seconds, error_message, feature_file_at_run, doors_number_at_run, retry_attempt, screenshot_path, video_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [run_id, s["uid"], s["name"], s["status"], s["duration"], s["error"], s["feature_file"], s["doors_id"], s["total_attempts"], s.get("screenshot_path"), s.get("video_path")],
            )
            if s.get("doors_id"):
                upsert_scenario_history(
                    conn,
                    doors_number=s["doors_id"],
                    scenario_uid=s["uid"],
                    name=s["name"],
                    run_id=run_id,
                    status=s["status"],
                    version=effective_version,
                    timestamp=started_at or finished_at,
                )
        # Write manifest JSON with full metadata
        _write_manifest_json(run_id, options, all_scenarios, passed, failed, skipped, started_at or finished_at, effective_version)
    finally:
        conn.close()


def _save_results_to_duckdb(run_id: str, options: TestRunOptions, started_at: datetime | None = None, allure_dir: str | None = None) -> dict:
    """Parse allure-results JSON and insert run/scenario rows into DuckDB."""
    import hashlib

    effective_allure_dir = Path(allure_dir) if allure_dir else Path(os.getenv("ALLURE_RESULTS_DIR", str(PROJECT_ROOT / MAVEN_MODULE / "target" / "allure-results")))
    print(f"[INFO] allure_dir={effective_allure_dir}  exists={effective_allure_dir.exists()}")
    if effective_allure_dir.exists():
        files = list(effective_allure_dir.glob("*-result.json"))
        print(f"[INFO] result files found: {len(files)}")

    # Fallback: read version from environment.properties if not provided in options
    effective_version = options.version or ""
    if not effective_version and effective_allure_dir.exists():
        env_props = effective_allure_dir / "environment.properties"
        if env_props.exists():
            for line in env_props.read_text(errors="replace").splitlines():
                key, _, val = line.partition("=")
                if key.strip().lower() == "version":
                    effective_version = val.strip()
                    break

    # Group results by identity_key to detect retries (multiple attempts).
    # Only include files whose start timestamp is within the current run window to
    # avoid mixing results from previous Maven invocations that weren't cleaned up.
    # The window is: [started_at - 5 min, now+1 min]. If started_at is unknown we
    # use a generous 24-hour window anchored at the newest file's timestamp.
    grouped: dict[str, list[dict]] = {}
    all_scenarios = []

    if effective_allure_dir.exists():
        all_parsed = []
        for result_file in sorted(effective_allure_dir.glob("*-result.json")):
            parsed = _parse_allure_result(result_file)
            if parsed is not None:
                all_parsed.append(parsed)

        # Determine the run window anchor
        if all_parsed:
            newest_ts_ms = max(p["start_ts_ms"] for p in all_parsed)
            if started_at:
                window_start_ms = int(started_at.timestamp() * 1000) - 5 * 60 * 1000
            else:
                # No known start time — take only files within 24 h of the newest file
                window_start_ms = newest_ts_ms - 24 * 3600 * 1000
            window_end_ms = newest_ts_ms + 60 * 1000

            for parsed in all_parsed:
                ts = parsed["start_ts_ms"]
                if ts == 0 or window_start_ms <= ts <= window_end_ms:
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

        # Copy this scenario's attachment files once; build servable paths.
        att_paths: dict[str, str | None] = {}
        atts = []
        for a in final.get("attachments", []):
            src = a["source"]
            if src not in att_paths:
                att_paths[src] = _copy_run_attachment(effective_allure_dir, run_id, src)
            if att_paths[src]:
                atts.append({"name": a["name"], "type": a["type"], "path": att_paths[src]})
        screenshot_path = att_paths.get(final.get("screenshot_source"))
        video_path = att_paths.get(final.get("video_source"))

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
            "steps": final["steps"],
            "screenshot_path": screenshot_path,
            "video_path": video_path,
            "attachments": atts,
        }
        all_scenarios.append(scenario_map[key])

    # Count statuses
    passed = sum(1 for s in all_scenarios if s["status"] == "PASSED")
    failed = sum(1 for s in all_scenarios if s["status"] in {"FAILED", "BROKEN"})
    skipped = sum(1 for s in all_scenarios if s["status"] == "SKIPPED")
    finished_at = datetime.now()

    _persist_run(run_id, options, all_scenarios, passed, failed, skipped, effective_version, started_at, finished_at)

    return {"total": len(all_scenarios), "passed": passed, "failed": failed, "skipped": skipped}


def _write_manifest_json(run_id: str, options: TestRunOptions, scenarios: list, passed: int, failed: int, skipped: int, ts: datetime, effective_version: str = "") -> None:
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
        "version": effective_version or options.version or "",
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
                # Only types allowed by the Attachment model, else load_manifests
                # would fail validation for the whole run.
                "attachments": [
                    a for a in s.get("attachments", [])
                    if a.get("type") in ("image/png", "video/mp4", "text/plain")
                ],
                "attempts": s.get("attempt_list", []),
                "dependencies": s.get("dependencies", []),
                "is_flaky": s.get("is_flaky", False),
                "errorMessage": s.get("error") or "",
            }
            for i, s in enumerate(scenarios)
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))


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


class JiraResponse(BaseModel):
    jiraKey: str
    jiraUrl: Optional[str] = None


class BugCreateRequest(BaseModel):
    scenarioName: str
    runId: str


class BugCreateResponse(BaseModel):
    jiraKey: str
    doorsNumber: str


class DoorsRunRequest(BaseModel):
    script: str


def _run_email_context(run_id: str) -> dict:
    """Build the test_report.html email context for a run.

    Pulls real totals from the DuckDB ``runs`` row, falling back to the run
    manifest, then to zeros — so the email always sends (the previous code
    hardcoded zeros, producing a meaningless 0/0 report)."""
    total = passed = failed = skipped = 0
    started_at = ""
    try:
        with get_connection(read_only=True) as conn:
            row = conn.execute(
                "SELECT total_scenarios, passed, failed, skipped, started_at FROM runs WHERE id = ?",
                [run_id],
            ).fetchone()
        if row:
            total, passed, failed, skipped = row[0] or 0, row[1] or 0, row[2] or 0, row[3] or 0
            started_at = row[4].isoformat() if row[4] else ""
        else:
            manifest = next((m for m in load_manifests() if m.runId == run_id), None)
            if manifest:
                total, passed, failed, skipped = (
                    manifest.totalScenarios, manifest.passed, manifest.failed, manifest.skipped,
                )
                started_at = manifest.timestamp.isoformat() if manifest.timestamp else ""
    except Exception:
        pass
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "started_at": started_at,
        "dashboard_url": f"http://localhost:8000/reports/{run_id}",
    }


MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Route modules split out of this file (see routes/). Imported here, after every
# shared symbol above is defined, so each module's `import server` + server.X
# references resolve with no import cycle.
from routes.bugs import router as bugs_router  # noqa: E402
from routes.integrations import router as integrations_router  # noqa: E402
from routes.runs import router as runs_router  # noqa: E402
from routes.system import router as system_router  # noqa: E402
from routes.admin import router as admin_router  # noqa: E402
from routes.reports import router as reports_router  # noqa: E402
from routes.triage import router as triage_router  # noqa: E402
from routes.tests import router as tests_router  # noqa: E402
from routes.pages import router as pages_router  # noqa: E402
app.include_router(bugs_router)
app.include_router(integrations_router)
app.include_router(runs_router)
app.include_router(system_router)
app.include_router(admin_router)
app.include_router(reports_router)
app.include_router(triage_router)
app.include_router(tests_router)
app.include_router(pages_router)
