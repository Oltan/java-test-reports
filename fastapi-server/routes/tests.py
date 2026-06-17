"""Test run-management routes (start, running, jobs, cancel), split out of
server.py.

This is the most heavily monkeypatched group, so EVERYTHING shared is referenced
as server.X — get_connection, _spawn_run, TEST_MAX_CONCURRENCY, tests_lock,
running_tests, _terminate_proc, _worker_specs/_worker_options, _broadcast_state —
so patch.object(server, ...) in the tests still applies through this router.
"""
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

import server
from models import TestRunOptions

router = APIRouter()


@router.post("/api/tests/start", dependencies=[Depends(server.verify_token)])
async def start_tests(options: TestRunOptions, background_tasks: BackgroundTasks):
    """Start tests with validated options. Invalid options are rejected by Pydantic."""
    del background_tasks
    job_id = f"job-{uuid4().hex[:8]}"
    now = datetime.now()
    run_ids = []
    workers = []
    specs = server._worker_specs(options)
    job_tags = options.tags if options.mode != "matrix" else " | ".join(dict.fromkeys(s[0] for s in specs))

    with server.tests_lock:
        with server.get_connection(read_only=False) as conn:
            server.init_schema(conn)
            if not options.force:
                dup = conn.execute(
                    "SELECT job_id FROM jobs WHERE tags = ? AND environment = ? "
                    "AND status IN ('queued', 'running') LIMIT 1",
                    [job_tags, options.environment],
                ).fetchone()
                if dup:
                    raise HTTPException(
                        status_code=409,
                        detail=f"A run with these tags and environment is already active "
                               f"(job {dup[0]}). Pass force=true to start anyway.",
                    )
            running = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = 'running'"
            ).fetchone()[0]
            admit = running < server.TEST_MAX_CONCURRENCY
            job_status = "running" if admit else "queued"
            conn.execute(
                """
                INSERT INTO jobs (job_id, requester, tags, retry_count, parallel, environment, version, browser, status, started_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [job_id, "engineer", job_tags, options.retry_count, len(specs),
                 options.environment, options.version, options.browser, job_status, now],
            )

            for i, (wtags, wbrowser, wenv, wfeatures) in enumerate(specs):
                run_id = f"test-{uuid4().hex[:8]}"
                worker_id = f"{job_id}-w{i}"
                output_dir = str(server.PROJECT_ROOT / server.MAVEN_MODULE / "target" / f"allure-results-{run_id}")
                conn.execute(
                    """
                    INSERT INTO worker_runs (worker_id, job_id, run_id, shard, status, output_dir, started_at, tags, browser, environment, features)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [worker_id, job_id, run_id, i, job_status, output_dir, now, wtags, wbrowser, wenv, wfeatures],
                )
                run_ids.append(run_id)
                workers.append({"worker_id": worker_id, "run_id": run_id, "shard": i,
                                "output_dir": output_dir, "tags": wtags, "browser": wbrowser,
                                "environment": wenv, "features": wfeatures})

            conn.commit()

        if admit:
            for worker in workers:
                wopts = server._worker_options(worker["tags"], worker["browser"], worker["environment"],
                                               options.retry_count, options.version, worker["features"])
                server._spawn_run(worker["run_id"], wopts, worker["output_dir"])

    for run_id in run_ids:
        await server._broadcast_state(run_id, job_status, job_id=job_id)

    return {
        "job_id": job_id,
        "workers": workers,
        "runs": run_ids,
        "status": "started" if admit else "queued",
        "mode": "serialized_safe",
        "parallel": len(specs),
    }


@router.get("/api/tests/discovery", dependencies=[Depends(server.verify_token)])
def discovery(tags: str = "@smoke", shards: int = 1):
    """Preview shard mode: discover scenarios (Cucumber dry-run, no browser) for
    the tag filter and show how their feature files split into `shards` groups."""
    scenarios = server._discover_scenarios(tags)
    features = list(dict.fromkeys(s["feature"] for s in scenarios))
    plan = server._shard_features(features, shards)
    return {
        "tags": tags,
        "count": len(scenarios),
        "scenarios": scenarios,
        "features": features,
        "shards": [{"features": s, "count": len(s)} for s in plan],
    }


@router.get("/api/tests/running", dependencies=[Depends(server.verify_token)])
async def list_running_tests():
    with server.get_connection(read_only=False) as conn:
        server.init_schema(conn)
        rows = conn.execute(
            """
            SELECT j.job_id, j.tags, j.retry_count, j.parallel, j.environment, j.version, j.started_at,
                   w.worker_id, w.run_id, w.shard, w.status as worker_status, w.output_dir, j.status
            FROM jobs j
            JOIN worker_runs w ON j.job_id = w.job_id
            WHERE j.status IN ('running', 'queued')
            ORDER BY j.status DESC, j.started_at DESC
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
                "status": row[12],
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
    running_ids = [jid for jid, j in jobs_map.items() if j["status"] == "running"]
    return {"running": running_ids, "jobs": jobs, "count": len(jobs)}


@router.get("/api/tests/jobs", dependencies=[Depends(server.verify_token)])
async def list_all_jobs():
    with server.get_connection(read_only=False) as conn:
        server.init_schema(conn)
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


@router.post("/api/tests/{run_id}/cancel", dependencies=[Depends(server.verify_token)])
async def cancel_test(run_id: str):
    now = datetime.now()
    with server.get_connection(read_only=False) as conn:
        worker_row = conn.execute(
            "SELECT worker_id, job_id FROM worker_runs WHERE run_id = ?",
            [run_id],
        ).fetchone()
        if not worker_row:
            return {"status": "not_found", "run_id": run_id}
        worker_id, job_id = worker_row[0], worker_row[1]

        conn.execute(
            "UPDATE worker_runs SET status = 'cancelled', ended_at = ? WHERE job_id = ?",
            [now, job_id],
        )
        conn.execute(
            "UPDATE jobs SET status = 'cancelled', ended_at = ? WHERE job_id = ?",
            [now, job_id],
        )
        job_run_ids = {r[0] for r in conn.execute(
            "SELECT run_id FROM worker_runs WHERE job_id = ?", [job_id]
        ).fetchall()}
        conn.commit()

    with server.tests_lock:
        cancelled_run_ids = []
        for rid, proc in list(server.running_tests.items()):
            if rid in job_run_ids:
                poll = getattr(proc, "poll", None)
                returncode = poll() if callable(poll) else getattr(proc, "returncode", None)
                if returncode is None:
                    server._terminate_proc(proc)
                cancelled_run_ids.append(rid)
        for rid in cancelled_run_ids:
            server.running_tests.pop(rid, None)

    return {"status": "cancelled", "run_id": run_id, "job_id": job_id}


@router.post("/api/tests/job/{job_id}/cancel", dependencies=[Depends(server.verify_token)])
async def cancel_job(job_id: str):
    now = datetime.now()
    with server.get_connection(read_only=False) as conn:
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

    with server.tests_lock:
        for rid in worker_run_ids:
            proc = server.running_tests.pop(rid, None)
            if proc:
                poll = getattr(proc, "poll", None)
                returncode = poll() if callable(poll) else getattr(proc, "returncode", None)
                if returncode is None:
                    server._terminate_proc(proc)

    return {"status": "cancelled", "job_id": job_id}
