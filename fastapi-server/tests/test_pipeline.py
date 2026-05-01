from unittest.mock import AsyncMock, patch


def test_pipeline_run_endpoint(client):
    with patch("server.execute_pipeline") as execute_pipeline:
        resp = client.post("/api/pipeline/run?run_id=test-001")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    assert "run_id" in data or "job_id" in data
    assert data["run_id"] == "test-001"
    execute_pipeline.assert_called_once_with("test-001")


def test_pipeline_status_endpoint(client):
    resp = client.get("/api/pipeline/status/test-001")

    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == "test-001"
    assert "stages" in data


def test_tfs_trigger_endpoint_uses_mock_client(client):
    with patch("tfs_client.tfs.trigger_pipeline", new_callable=AsyncMock) as trigger_pipeline:
        trigger_pipeline.return_value = {"id": 67890}
        resp = client.post(
            "/api/tfs/trigger",
            json={"pipeline_id": 7, "variables": {"CUCUMBER_TAGS": "@smoke"}},
        )

    assert resp.status_code == 200
    assert resp.json() == {"run_id": 67890, "status": "queued"}
    trigger_pipeline.assert_awaited_once_with(7, {"CUCUMBER_TAGS": "@smoke"})
