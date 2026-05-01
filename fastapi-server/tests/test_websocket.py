import server


def test_websocket_endpoint_tracks_connection(client):
    run_id = "ws-test-001"

    with client.websocket_connect(f"/ws/test-status/{run_id}"):
        assert run_id in server.ws_manager.active_connections
        assert len(server.ws_manager.active_connections[run_id]) == 1

    assert run_id not in server.ws_manager.active_connections
