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

def test_broadcast_mirrors_to_live_without_per_run_subscriber():
    """Regression: a state frame must reach the shared 'live' channel even when
    the specific run has no direct subscriber (the admin panel watches 'live')."""
    import asyncio
    from websocket_handler import ConnectionManager

    class _FakeWS:
        def __init__(self):
            self.sent = []
        async def send_json(self, message):
            self.sent.append(message)

    mgr = ConnectionManager()
    live_ws = _FakeWS()
    mgr.active_connections["live"] = [live_ws]

    asyncio.run(mgr.broadcast("run-no-subscriber", {"type": "state", "status": "running"}))

    assert {"type": "state", "status": "running"} in live_ws.sent
