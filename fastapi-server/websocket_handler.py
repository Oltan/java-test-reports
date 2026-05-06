"""WebSocket handler for real-time test status streaming."""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ConnectionManager:
    """Manages WebSocket connections grouped by run_id."""

    def __init__(self) -> None:
        self.active_connections: dict[str, list[WebSocket]] = {}
        self.last_messages: dict[str, dict] = {}

    async def connect(self, run_id: str, ws: WebSocket) -> None:
        await ws.accept()
        if run_id not in self.active_connections:
            self.active_connections[run_id] = []
        self.active_connections[run_id].append(ws)
        if run_id in self.last_messages:
            await ws.send_json(self.last_messages[run_id])
        logger.info("WebSocket connected for run_id=%s (%d connections)", run_id, len(self.active_connections[run_id]))

    def disconnect(self, run_id: str, ws: WebSocket) -> None:
        if run_id in self.active_connections:
            if ws in self.active_connections[run_id]:
                self.active_connections[run_id].remove(ws)
            logger.info(
                "WebSocket disconnected for run_id=%s (%d remaining)", run_id, len(self.active_connections[run_id])
            )
            if not self.active_connections[run_id]:
                del self.active_connections[run_id]

    async def broadcast(self, run_id: str, message: dict) -> None:
        self.last_messages[run_id] = message
        if run_id not in self.active_connections:
            return
        stale: list[WebSocket] = []
        for ws in list(self.active_connections[run_id]):
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)
        for ws in stale:
            if ws in self.active_connections.get(run_id, []):
                self.active_connections[run_id].remove(ws)
        if not self.active_connections[run_id]:
            del self.active_connections[run_id]
        if run_id != "live" and "live" in self.active_connections:
            live_stale: list[WebSocket] = []
            for ws in list(self.active_connections["live"]):
                try:
                    await ws.send_json(message)
                except Exception:
                    live_stale.append(ws)
            for ws in live_stale:
                if ws in self.active_connections.get("live", []):
                    self.active_connections["live"].remove(ws)


manager = ConnectionManager()


async def stream_test_output(run_id: str, tags: str = "@smoke") -> dict:
    """Run Maven test and broadcast real-time results via WebSocket.

    Spawns ``mvn -pl test-core test`` as an async subprocess, parses each
    stdout line for scenario status markers, and pushes incremental
    result dicts to every WebSocket client subscribed to *run_id*.

    Returns the final results dict when the subprocess finishes.
    """
    maven_bin = os.getenv("MAVEN_BIN", "mvn")
    cmd = [maven_bin, "-pl", "test-core", "test", f"-Dcucumber.filter.tags={tags}"]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(PROJECT_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    results: dict = {
        "run_id": run_id,
        "tags": tags,
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "scenarios": [],
        "finished": False,
    }

    await manager.broadcast(run_id, {"type": "status", "data": results})

    assert proc.stdout is not None
    async for line in proc.stdout:
        decoded = line.decode(errors="replace").strip()
        if not decoded:
            continue

        # Detect scenario result lines from Maven/Surefire output
        scenario_entry: Optional[dict] = None
        if "Scenario:" in decoded or "Scenario Outline:" in decoded:
            results["total"] += 1
            scenario_entry = {"name": decoded, "status": "running"}
            results["scenarios"].append(scenario_entry)
        elif "PASSED" in decoded:
            results["passed"] += 1
            if results["scenarios"]:
                results["scenarios"][-1]["status"] = "passed"
        elif "FAILED" in decoded:
            results["failed"] += 1
            if results["scenarios"]:
                results["scenarios"][-1]["status"] = "failed"
        elif "SKIPPED" in decoded:
            results["skipped"] += 1
            if results["scenarios"]:
                results["scenarios"][-1]["status"] = "skipped"

        await manager.broadcast(run_id, {"type": "update", "data": results})

    await proc.wait()

    results["finished"] = True
    results["exit_code"] = proc.returncode
    await manager.broadcast(run_id, {"type": "complete", "data": results})

    return results
