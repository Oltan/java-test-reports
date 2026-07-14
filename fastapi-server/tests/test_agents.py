import os
from pathlib import Path
from unittest.mock import patch

import duckdb
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "test-secret")

import server
from db import NonClosingConnectionWrapper, init_schema
from server import app, create_token

client = TestClient(app)
RUN_ID = "agent-run-1"


def _auth() -> dict:
    return {"Authorization": f"Bearer {create_token('admin')}"}


def _seeded_conn():
    conn = duckdb.connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO runs (id, version, environment, started_at) VALUES (?, 'v1', 'staging', current_timestamp)",
        [RUN_ID],
    )
    conn.execute(
        """INSERT INTO scenario_definitions
           (scenario_uid, identity_source, identity_key, current_name, current_feature_file, current_feature_line, doors_number)
           VALUES ('uid-agent', 'doors', 'DOORS-9', 'Agent scenario fails', 'features/unit-demo.feature', 15, 'DOORS-9')"""
    )
    conn.execute(
        """INSERT INTO scenario_results
           (run_id, scenario_uid, name_at_run, status, error_message, doors_number_at_run)
           VALUES (?, 'uid-agent', 'Agent scenario fails', 'FAILED', 'expected true but was false', 'DOORS-9')""",
        [RUN_ID],
    )
    return NonClosingConnectionWrapper(conn)


class FakeOpenCode:
    def status(self):
        return {"configured": True, "command": "opencode", "executable": "/bin/opencode"}

    def is_configured(self):
        return True

    def run(self, prompt, *, agent="repair"):
        class Result:
            command = ["opencode", "run", "--format", "json", "<prompt>"]
            exit_code = 0
            stdout = '{"decision":"CREATE_JIRA","confidence":0.82}'
            stderr = ""
            parsed = {"decision": "CREATE_JIRA", "confidence": 0.82}
        assert "Agent scenario fails" in prompt
        return Result()


class MissingOpenCode:
    def status(self):
        return {"configured": False, "command": "opencode", "executable": None}

    def is_configured(self):
        return False


def test_opencode_status_requires_auth():
    response = client.get("/api/agent/opencode/status")

    assert response.status_code == 401


def test_opencode_status_returns_config(monkeypatch):
    monkeypatch.setattr(server, "opencode_agent", FakeOpenCode())

    response = client.get("/api/agent/opencode/status", headers=_auth())

    assert response.status_code == 200
    assert response.json()["configured"] is True


def test_agent_advise_returns_opencode_decision(monkeypatch):
    log_dir = Path(server.MANIFESTS_DIR) / RUN_ID
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "console.log").write_text("expected true but was false\n", encoding="utf-8")
    conn = _seeded_conn()
    monkeypatch.setattr(server, "opencode_agent", FakeOpenCode())
    with patch.object(server, "get_connection", lambda read_only=False: conn):
        response = client.post(
            f"/api/agent/runs/{RUN_ID}/advise",
            headers=_auth(),
            json={"intent": "jira"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["advice"]["decision"] == "CREATE_JIRA"
    assert body["scenario_uid"] == "uid-agent"


def test_agent_advise_returns_503_when_opencode_missing(monkeypatch):
    monkeypatch.setattr(server, "opencode_agent", MissingOpenCode())

    response = client.post(f"/api/agent/runs/{RUN_ID}/advise", headers=_auth(), json={})

    assert response.status_code == 503
