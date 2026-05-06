import os
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")

import server
from server import create_token
from fastapi.testclient import TestClient


def test_websocket_endpoint_tracks_connection():
    run_id = "ws-test-001"
    token = create_token("admin")

    with TestClient(server.app).websocket_connect(f"/ws/test-status/{run_id}?token={token}"):
        assert run_id in server.ws_manager.active_connections
        assert len(server.ws_manager.active_connections[run_id]) == 1

    assert run_id not in server.ws_manager.active_connections