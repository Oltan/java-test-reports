import os
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")

from server import app

client = TestClient(app)


def test_tfs_trigger_endpoint_returns_run_id():
    with patch("tfs_client.tfs.trigger_pipeline", new_callable=AsyncMock) as trigger_pipeline:
        trigger_pipeline.return_value = {"id": 12345}
        response = client.post(
            "/api/tfs/trigger",
            json={"pipeline_id": 42, "variables": {"CUCUMBER_TAGS": "@smoke"}},
        )

    assert response.status_code == 200
    assert response.json() == {"run_id": 12345, "status": "queued"}
    trigger_pipeline.assert_awaited_once_with(42, {"CUCUMBER_TAGS": "@smoke"})


def test_tfs_webhook_acknowledges_payload():
    response = client.post("/api/tfs/webhook", json={"eventType": "build.complete"})

    assert response.status_code == 200
    assert response.json() == {"received": True}


def test_tfs_status_endpoint_returns_run_status():
    status_payload = {"id": 12345, "state": "completed", "result": "succeeded"}
    with patch("tfs_client.tfs.get_run_status", new_callable=AsyncMock) as get_run_status:
        get_run_status.return_value = status_payload
        response = client.get("/api/tfs/status/42/12345")

    assert response.status_code == 200
    assert response.json() == status_payload
    get_run_status.assert_awaited_once_with(42, 12345)
