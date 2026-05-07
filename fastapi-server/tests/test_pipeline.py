import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import os
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")

from server import app, create_token
from fastapi.testclient import TestClient

client = TestClient(app)


def _auth_headers():
    token = create_token("admin")
    return {"Authorization": f"Bearer {token}"}


def test_pipeline_run_endpoint():
    with patch("server.execute_pipeline") as execute_pipeline:
        resp = client.post("/api/pipeline/run?run_id=test-001", headers=_auth_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    assert "run_id" in data or "job_id" in data
    assert data["run_id"] == "test-001"
    execute_pipeline.assert_called_once_with("test-001")


def test_pipeline_status_endpoint():
    resp = client.get("/api/pipeline/status/test-001", headers=_auth_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == "test-001"
    assert "stages" in data


def test_maven_test_stage_uses_custom_command(monkeypatch):
    from pipeline import PipelineRunner

    monkeypatch.setenv("PIPELINE_MAVEN_COMMAND", "mvn -pl test-core test")
    runner = PipelineRunner("run-001")

    captured = []

    async def fake_run_shell(cmd):
        captured.append(cmd)

    runner._run_shell_command = fake_run_shell

    import asyncio
    asyncio.run(runner.run_maven_tests())

    assert captured == ["mvn -pl test-core test"]


def test_maven_test_stage_auto_detects_mvn(monkeypatch):
    from pipeline import PipelineRunner

    monkeypatch.delenv("PIPELINE_MAVEN_COMMAND", raising=False)
    monkeypatch.setenv("MAVEN_CMD", "/usr/bin/mvn")
    monkeypatch.setenv("MAVEN_MODULE", "test-core")
    runner = PipelineRunner("run-002")

    captured = []

    async def fake_run_exec(cmd):
        captured.append(cmd)

    runner._run_exec_command = fake_run_exec

    import asyncio
    asyncio.run(runner.run_maven_tests())

    assert captured == [["/usr/bin/mvn", "-pl", "test-core", "test"]]


def test_maven_test_stage_default_module(monkeypatch):
    from pipeline import PipelineRunner

    monkeypatch.delenv("PIPELINE_MAVEN_COMMAND", raising=False)
    monkeypatch.setenv("MAVEN_CMD", "mvn")
    monkeypatch.delenv("MAVEN_MODULE", raising=False)
    runner = PipelineRunner("run-003")

    captured = []

    async def fake_run_exec(cmd):
        captured.append(cmd)

    runner._run_exec_command = fake_run_exec

    import asyncio
    asyncio.run(runner.run_maven_tests())

    assert captured == [["mvn", "-pl", "test-core", "test"]]


def test_tfs_trigger_endpoint_uses_mock_client():
    with patch("tfs_client.tfs.trigger_pipeline", new_callable=AsyncMock) as trigger_pipeline:
        trigger_pipeline.return_value = {"id": 67890}
        resp = client.post(
            "/api/tfs/trigger",
            json={"pipeline_id": 7, "variables": {"CUCUMBER_TAGS": "@smoke"}},
            headers=_auth_headers(),
        )

    assert resp.status_code == 200
    assert resp.json() == {"run_id": 67890, "status": "queued"}
    trigger_pipeline.assert_awaited_once_with(7, {"CUCUMBER_TAGS": "@smoke"})