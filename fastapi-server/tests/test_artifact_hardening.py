from html.parser import HTMLParser

from fastapi.testclient import TestClient

import server
from server import app, create_token, jinja_env


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        for name, value in attrs:
            if name == "href" and value is not None:
                self.links.append(value)


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token('engineer')}"}


def test_anonymous_raw_report_artifact_path_is_denied(tmp_path, monkeypatch):
    artifacts = tmp_path / "some-run-id"
    artifacts.mkdir()
    (artifacts / "screenshot.png").write_bytes(b"not-a-real-image")
    monkeypatch.setattr(server, "MANIFESTS_DIR", tmp_path)

    response = TestClient(app, follow_redirects=False).get("/reports/some-run-id/screenshot.png")

    assert response.status_code in {302, 401, 403, 404}


def test_public_report_template_has_no_raw_report_artifact_links():
    html = jinja_env.get_template("public_report.html").render(
        run_id="public-run",
        scenarios=[("Checkout hides /reports/private/screenshot.png", "FAILED", 1.2)],
        total_scenarios=1,
        total_passed=0,
        total_failed=1,
        total_skipped=0,
    )
    parser = _LinkCollector()
    parser.feed(html)

    assert all(not href.startswith("/reports/") for href in parser.links)
    assert '<a href="/reports/' not in html


def test_engineer_token_can_fetch_internal_report_attachment(tmp_path, monkeypatch):
    artifacts = tmp_path / "some-run-id"
    artifacts.mkdir()
    attachment = artifacts / "screenshot.png"
    attachment.write_bytes(b"engineer-only artifact")
    monkeypatch.setattr(server, "MANIFESTS_DIR", tmp_path)

    response = TestClient(app).get(
        "/reports/some-run-id/screenshot.png",
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert response.content == b"engineer-only artifact"


def test_report_artifact_path_traversal_is_not_served(tmp_path, monkeypatch):
    secret = tmp_path.parent / "outside.log"
    secret.write_text("do not serve")
    monkeypatch.setattr(server, "MANIFESTS_DIR", tmp_path)

    response = TestClient(app).get(
        "/reports/../outside.log",
        headers=_auth_headers(),
    )

    assert response.status_code == 404
