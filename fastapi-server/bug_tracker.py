import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any


class BugTracker:
    def __init__(self, path: str = "bug-tracker.json"):
        self.path = Path(path)
        self.lock = threading.Lock()
        self._ensure_file()

    def _ensure_file(self) -> None:
        if not self.path.exists():
            self.path.write_text('{"version": "1.0", "mappings": {}}')

    def _read(self) -> Dict[str, Any]:
        with self.lock:
            return json.loads(self.path.read_text())

    def _write(self, data: Dict[str, Any]) -> None:
        with self.lock:
            self.path.write_text(json.dumps(data, indent=2, default=str))

    def get(self, doors_number: str) -> Optional[Dict[str, Any]]:
        data = self._read()
        return data["mappings"].get(doors_number)

    def get_all(self) -> Dict[str, Any]:
        data = self._read()
        return data["mappings"]

    def register(self, doors_number: str, jira_key: str, scenario_name: str, run_id: str) -> Dict[str, Any]:
        data = self._read()
        now = datetime.now(timezone.utc).isoformat()
        existing = data["mappings"].get(doors_number, {})
        run_ids = existing.get("runIds", [])
        if run_id not in run_ids:
            run_ids.append(run_id)
        data["mappings"][doors_number] = {
            "jiraKey": jira_key,
            "status": "OPEN",
            "firstSeen": existing.get("firstSeen", now),
            "lastSeen": now,
            "scenarioName": scenario_name,
            "runIds": run_ids,
            "resolution": None
        }
        self._write(data)
        return data["mappings"][doors_number]