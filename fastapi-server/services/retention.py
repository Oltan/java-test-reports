"""Per-run artifact retention.

Every run leaves heavy directories on disk:

  {target_dir}/allure-results-{run_id}/   raw Allure output (per-run isolation, RM-1)
  {manifests_dir}/{run_id}/               attachments copied for /reports serving (P5)

DuckDB rows and the small {run_id}.json manifests are kept forever — history,
dashboards and triage keep working; only the heavy directories are removed, so
screenshots/videos of expired runs stop resolving (they 404).

Configuration (environment):
  RUN_RETENTION_DAYS      remove artifacts of terminal runs older than N days
                          (default 30; 0 disables the age rule)
  RUN_RETENTION_MAX_RUNS  additionally keep artifacts for at most the N newest
                          runs (default 0 = unlimited)

Runs that are still ``queued``/``running`` are never touched. Orphan recovery
must run before cleanup on startup so crashed runs are already ``interrupted``.
"""

import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

_ACTIVE_STATUSES = ("queued", "running")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _run_ages(get_connection) -> tuple[dict[str, datetime], set[str]]:
    """Return ({run_id: started_at}, {run_ids that are queued/running})."""
    ages: dict[str, datetime] = {}
    active: set[str] = set()
    with get_connection(read_only=False) as conn:
        for run_id, status, started_at in conn.execute(
            "SELECT run_id, status, started_at FROM worker_runs"
        ).fetchall():
            if started_at is not None:
                ages[run_id] = started_at
            if status in _ACTIVE_STATUSES:
                active.add(run_id)
        for run_id, started_at in conn.execute(
            "SELECT id, started_at FROM runs"
        ).fetchall():
            if started_at is not None and run_id not in ages:
                ages[run_id] = started_at
    return ages, active


def _candidate_dirs(target_dir: Path, manifests_dir: Path) -> dict[str, list[Path]]:
    """Map run_id -> artifact directories belonging to it."""
    candidates: dict[str, list[Path]] = {}
    if target_dir.is_dir():
        for path in target_dir.glob("allure-results-*"):
            if path.is_dir():
                run_id = path.name.removeprefix("allure-results-")
                candidates.setdefault(run_id, []).append(path)
    if manifests_dir.is_dir():
        for path in manifests_dir.iterdir():
            if path.is_dir():
                candidates.setdefault(path.name, []).append(path)
    return candidates


def cleanup_run_artifacts(get_connection, target_dir: Path, manifests_dir: Path,
                          now: datetime | None = None) -> dict:
    """Delete expired per-run artifact directories. Returns a summary dict."""
    days = _env_int("RUN_RETENTION_DAYS", 30)
    max_runs = _env_int("RUN_RETENTION_MAX_RUNS", 0)
    if days <= 0 and max_runs <= 0:
        return {"removed": [], "kept": 0, "disabled": True}

    now = now or datetime.now()
    try:
        ages, active = _run_ages(get_connection)
    except Exception:
        # DB unavailable: fall back to mtime-only ages; recent mtimes still
        # shield anything actively being written to.
        ages, active = {}, set()

    candidates = _candidate_dirs(target_dir, manifests_dir)

    def run_age(run_id: str, dirs: list[Path]) -> datetime:
        if run_id in ages:
            return ages[run_id]
        return datetime.fromtimestamp(min(p.stat().st_mtime for p in dirs))

    aged = sorted(
        ((rid, dirs, run_age(rid, dirs)) for rid, dirs in candidates.items() if rid not in active),
        key=lambda item: item[2], reverse=True,  # newest first
    )

    cutoff = now - timedelta(days=days) if days > 0 else None
    removed: list[str] = []
    for index, (run_id, dirs, age) in enumerate(aged):
        expired = cutoff is not None and age < cutoff
        over_cap = max_runs > 0 and index >= max_runs
        if not (expired or over_cap):
            continue
        for path in dirs:
            shutil.rmtree(path, ignore_errors=True)
        removed.append(run_id)

    return {"removed": removed, "kept": len(aged) - len(removed), "disabled": False}
