## 2026-05-01 — DuckDB migration

- `manifests/` contains 23 JSON files; current fixtures do not include feature line metadata, so migration uses `feature_file:feature_line` when present and falls back to `@id:`, DOORS number, feature/name, then scenario id.
- DuckDB install on this machine required `python3 -m pip install duckdb --break-system-packages` because Python is PEP 668 externally managed.
- Idempotency is enforced by `migration_imports` source file + SHA256 and by aborting when an existing `run_id` is seen with a different checksum.

## 2026-05-01 — FastAPI pipeline orchestrator

- FastAPI pipeline trigger uses `BackgroundTasks` and returns both `run_id` and `job_id` for orchestrator compatibility.
- `pipeline_status` has an FK to `runs(id)`, so the pipeline runner creates a minimal `runs` row before recording stage state.
- Optional external stages are configured through env command variables (`PIPELINE_*_COMMAND`); absent optional tools are recorded as `skipped` instead of breaking endpoint startup.

## 2026-05-01 — TFS REST client

- `fastapi-server/tfs_client.py` exposes `/api/tfs/*` through an `APIRouter`; `server.py` includes the router after `load_dotenv()` so Azure env vars are available before the module-level client is created.
- Trigger requests accept JSON body shape `{"pipeline_id": 1, "variables": {...}}`; variables are converted to Azure DevOps `{"name": {"value": "..."}}` format and verified with a curl smoke test against a local fake Azure endpoint.

## 2026-05-01 — FastAPI Jira Python client

- `fastapi-server/jira_client.py` now uses `atlassian-python-api` `Jira(url=..., token=...)` instead of raw `httpx`, keeps wiki-renderer descriptions as plain strings, and supports dry-run, DOORS-number JQL lookup, status, comments, attachments, and retry.
- The client accepts both new env names (`JIRA_URL`, `JIRA_PROJECT_KEY`) and legacy server env names (`JIRA_BASE_URL`, `JIRA_PROJECT`) so existing FastAPI startup paths remain compatible.

## 2026-05-01 — FastAPI multi-test launch

- `TestRunOptions` lives in `fastapi-server/models.py`; FastAPI/Pydantic rejects invalid tags, browser, environment, visibility, retry count, and parallel count before launch.
- `/api/tests/start` starts Maven from the project root and tracks each `subprocess.Popen` in a lock-protected `running_tests` map; cleanup runs in daemon watcher threads so the HTTP response returns immediately.
- Curl smoke verification can set `MAVEN_CMD=/usr/bin/true` to validate option handling and parallel run-id generation without executing real Cucumber tests.

## 2026-05-01 — FastAPI integration pytest suite

- Endpoint integration tests should patch `server.execute_pipeline`, `server.send_email`, and `tfs_client.tfs.*` to avoid real Maven/TFS/SMTP calls while still exercising FastAPI routing.
- `TestClient` executes FastAPI `BackgroundTasks` before returning control to pytest, so pipeline tests can assert the mocked `execute_pipeline(run_id)` call directly.
- WebSocket endpoint coverage can verify `ws_manager.active_connections` during a `websocket_connect` context and disconnect cleanup on context exit without sending `start`, which would invoke Maven streaming.
