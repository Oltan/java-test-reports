#!/usr/bin/env python3
"""Reference agent client for the Test Reports API (stdlib only).

Starts a test run, polls the job until it reaches a terminal state, then
prints per-run results and failure details. Intended both as a working CLI
and as copy-paste material for AI-agent integrations (see docs/API.md §6).

Auth (one of):
  REPORTS_TOKEN                    service/login token (recommended for agents;
                                   mint one via POST /api/admin/service-tokens)
  REPORTS_USER + REPORTS_PASSWORD  username/password login

Examples:
  REPORTS_TOKEN=eyJ... python3 scripts/agent_run.py --tags @smoke
  python3 scripts/agent_run.py --base-url http://qa-host:8000 --tags "@regression and not @wip"

Exit codes: 0 completed+green, 1 completed with failures, 2 job did not
complete (failed/cancelled/interrupted or wait timeout), 3 usage/HTTP error.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


def _request(base_url: str, path: str, token: str | None = None, payload: dict | None = None):
    req = urllib.request.Request(base_url.rstrip("/") + path)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data=data, timeout=30) as resp:
        return json.loads(resp.read().decode() or "null")


def login(base_url: str, username: str, password: str) -> str:
    out = _request(base_url, "/api/v1/auth/login", payload={"username": username, "password": password})
    return out["token"]


def start_run(base_url: str, token: str, args) -> dict:
    body = {"tags": args.tags, "browser": args.browser, "retry_count": args.retry_count,
            "parallel": args.parallel, "environment": args.environment}
    if args.force:
        body["force"] = True
    try:
        return _request(base_url, "/api/tests/start", token, body)
    except urllib.error.HTTPError as err:
        if err.code == 409:
            detail = json.loads(err.read().decode() or "{}")
            print(f"[agent] duplicate run rejected (409): {detail.get('detail')}\n"
                  f"[agent] re-run with --force to start anyway", file=sys.stderr)
            sys.exit(3)
        raise


def wait_for_job(base_url: str, token: str, job_id: str, timeout_s: int, interval_s: float) -> dict:
    deadline = time.monotonic() + timeout_s
    last_status = None
    while time.monotonic() < deadline:
        jobs = _request(base_url, "/api/tests/jobs", token)["jobs"]
        job = next((j for j in jobs if j["job_id"] == job_id), None)
        if job is None:
            raise RuntimeError(f"job {job_id} disappeared from /api/tests/jobs")
        if job["status"] != last_status:
            last_status = job["status"]
            print(f"[agent] job {job_id}: {last_status}")
        if job["status"] in TERMINAL:
            return job
        time.sleep(interval_s)
    print(f"[agent] timed out after {timeout_s}s waiting for job {job_id}", file=sys.stderr)
    sys.exit(2)


def report_runs(base_url: str, token: str, job: dict) -> int:
    """Print per-run summaries + failures; return total failed count."""
    total_failed = 0
    for worker in job["workers"]:
        run_id = worker["run_id"]
        try:
            run = _request(base_url, f"/api/v1/runs/{run_id}", token)
            summary = (f"total={run['totalScenarios']} passed={run['passed']} "
                       f"failed={run['failed']} skipped={run['skipped']}")
            total_failed += run["failed"]
        except urllib.error.HTTPError as err:
            if err.code != 404:
                raise
            # A run that produced no Allure results (e.g. 0 matching scenarios)
            # is never ingested, so it has no /api/v1/runs entry.
            print(f"[agent] run {run_id}: no ingested results (worker status: {worker['status']})")
            continue
        print(f"[agent] run {run_id}: {summary}")
        try:
            failures = _request(base_url, f"/api/v1/runs/{run_id}/failures", token)
        except urllib.error.HTTPError as err:
            if err.code != 404:
                raise
            failures = []
        for scenario in failures:
            print(f"[agent]   {scenario['status'].upper()}: {scenario['name']}")
            for step in scenario.get("steps", []):
                if step.get("status") in ("failed", "broken"):
                    error = (step.get("errorMessage") or "").strip().splitlines()
                    print(f"[agent]     step: {step['name']}" + (f" — {error[0]}" if error else ""))
    return total_failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=os.getenv("REPORTS_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--tags", default="@smoke")
    parser.add_argument("--browser", default="chrome")
    parser.add_argument("--environment", default="staging", choices=["staging", "prod", "dev"])
    parser.add_argument("--retry-count", type=int, default=0)
    parser.add_argument("--parallel", type=int, default=1)
    parser.add_argument("--force", action="store_true", help="bypass the duplicate-run 409 guard")
    parser.add_argument("--timeout", type=int, default=3600, help="max seconds to wait for the job")
    parser.add_argument("--poll-interval", type=float, default=5.0)
    args = parser.parse_args()

    token = os.getenv("REPORTS_TOKEN")
    if not token:
        user, password = os.getenv("REPORTS_USER"), os.getenv("REPORTS_PASSWORD")
        if not (user and password):
            print("set REPORTS_TOKEN, or REPORTS_USER + REPORTS_PASSWORD", file=sys.stderr)
            return 3
        token = login(args.base_url, user, password)

    started = start_run(args.base_url, token, args)
    job_id = started["job_id"]
    print(f"[agent] started job {job_id} ({started['status']}) runs={started['runs']}")

    job = wait_for_job(args.base_url, token, job_id, args.timeout, args.poll_interval)
    failed = report_runs(args.base_url, token, job)

    if job["status"] != "completed":
        print(f"[agent] job ended as {job['status']}", file=sys.stderr)
        return 2
    print(f"[agent] job completed — {'GREEN' if failed == 0 else f'{failed} failure(s)'}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.HTTPError as err:
        print(f"[agent] HTTP {err.code} on {err.url}: {err.read().decode()[:500]}", file=sys.stderr)
        sys.exit(3)
    except urllib.error.URLError as err:
        print(f"[agent] connection failed: {err.reason}", file=sys.stderr)
        sys.exit(3)
