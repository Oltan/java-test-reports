def test_versions_endpoint(client):
    resp = client.get("/api/versions")

    assert resp.status_code == 200
    assert "versions" in resp.json()


def test_metrics_endpoint(client):
    resp = client.get("/api/dashboard/metrics")

    assert resp.status_code == 200
    data = resp.json()
    assert "success_rate" in data
    assert "total_runs" in data


def test_home_dashboard_returns_html(client):
    resp = client.get("/")

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
