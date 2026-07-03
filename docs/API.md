# API Reference — Test Reports Automation System

> Not (Türkçe): Bu belge kasıtlı olarak İngilizce yazılmıştır; yapay zeka
> ajanlarının (AI agent) doğrudan tüketimi için hazırlanmıştır. Diğer tüm
> belgeler Türkçedir (bkz. `docs/RUNBOOK.md`).

This document describes the `fastapi-server` HTTP + WebSocket API well enough
for an external AI agent or engineer to integrate **without reading the
source**. It is verified against `fastapi-server/server.py`,
`fastapi-server/models.py`, `fastapi-server/routes/*.py`, and
`fastapi-server/websocket_handler.py`.

## 1. Overview

- **Base URL**: the server is a single FastAPI process, typically
  `http://localhost:8000` in dev (see `docs/RUNBOOK.md` for production
  deployment). All paths below are relative to that base URL.
- **Content type**: JSON request/response bodies unless noted otherwise
  (WebSocket messages are JSON frames; CSV export endpoints exist but are out
  of scope here).
- **Process model**: the server must run as a single process (`--workers 1`).
  In-memory state (`running_tests`, WebSocket connections, the queue
  semaphore) is not shared across workers — see `docs/RUNBOOK.md` §2.
- **Route layout**: routes live under `fastapi-server/routes/*.py`
  (`tests.py`, `admin.py`, `system.py`, `runs.py`, ...), each importing
  `server` for shared state/helpers (`server.get_connection`,
  `server.verify_token`, `server.tests_lock`, ...).
- This file intentionally skips the triage/Jira/DOORS/email/share endpoints
  (`/api/triage/*`, `/api/doors/*`, `/api/email/*`, `/api/reports/generate-share`,
  `/api/public/reports/*`, CSV export) — see "Other endpoints" note at the end.

## 2. Authentication

### 2.1 Login

```
POST /api/v1/auth/login
Content-Type: application/json

{"username": "admin", "password": "admin123"}
```

Response `200`:

```json
{"token": "<jwt>"}
```

The server also sets an `HttpOnly` cookie (`access_token`, `samesite=lax`,
`max_age=JWT_EXPIRATION_HOURS*3600`) for browser sessions — API/agent clients
should ignore the cookie and use the `token` field as a Bearer credential.

Credential resolution order (`routes/system.py: login`):
1. `users` table (DuckDB, PBKDF2-HMAC-SHA256, 600k iterations) — role stored
   per row. Best-effort: any DB error here falls straight through to step 2
   instead of a 500.
2. Fallback: env vars `ADMIN_USERNAME` / `ADMIN_PASSWORD` (default
   `admin` / `admin123`) → role `admin`.

`401` on invalid credentials:

```json
{"detail": "Invalid credentials"}
```

### 2.2 Using the token

Send it as a Bearer token on every protected route:

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/tests/running
```

### 2.3 Roles

JWT payload: `sub` (username), `role`, `exp`, `iat` (HS256, secret
`JWT_SECRET`, default lifetime `JWT_EXPIRATION_HOURS=24`). `TokenData.role`
defaults to `"runner"` if absent from the token.

| Role | How obtained | Can do |
|---|---|---|
| `admin` | seeded via `ADMIN_USERNAME`/`ADMIN_PASSWORD` login fallback, or created via `POST /api/admin/users` with `role: "admin"` | everything, plus `/api/admin/*` routes (`require_role("admin")`) |
| `runner` | default role for users created via `/api/admin/users` without `role: "admin"` | all non-admin authenticated routes (start/monitor/cancel tests, view runs) |
| `agent` | minted via `POST /api/admin/service-tokens` (admin-only) | same authenticated-route access as `runner` — intended for machine/service clients |

`require_role(*roles)` returns `403` if the token's role isn't in the allowed
set:

```json
{"detail": "Requires role in ['admin']"}
```

### 2.4 Service tokens (for AI agents / automation)

An admin mints a long-lived, stateless JWT for a named service/agent client:

```bash
curl -X POST http://localhost:8000/api/admin/service-tokens \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"name": "ci-agent", "days": 365}'
```

Request body (`ServiceTokenRequest`, `routes/admin.py`):

| Field | Type | Default | Validation |
|---|---|---|---|
| `name` | string | *(required)* | pattern `^[a-z0-9][a-z0-9_-]{1,31}$` — lowercase alphanumeric start, then 1-31 more of `[a-z0-9_-]` (total length 2-32) |
| `days` | int \| null | `SERVICE_TOKEN_DAYS` env var (default `365`) if omitted | `1 <= x <= 3650` |

Response `200` (`ServiceTokenResponse`):

```json
{
  "token": "<jwt>",
  "name": "ci-agent",
  "sub": "svc:ci-agent",
  "role": "agent",
  "expires_at": "2027-07-03T10:00:00+00:00"
}
```

The issued token's `sub` claim is `svc:<name>` and `role` is `"agent"`. Use
the `token` field exactly like a login token:

```bash
curl -H "Authorization: Bearer $SERVICE_TOKEN" http://localhost:8000/api/tests/running
```

Notes:
- Tokens are **stateless JWTs** — there is no server-side token store or
  revocation list. A minted token remains valid until it expires (`days`) or
  until `JWT_SECRET` is rotated (which invalidates *all* outstanding tokens,
  including normal login tokens).
- Only `admin` role can call this endpoint (`require_role("admin")`).
- Regular login tokens expire after `JWT_EXPIRATION_HOURS` (default 24h);
  service tokens are meant to outlive that for unattended agents — pass a
  larger `days` value accordingly.

### 2.5 User management (admin only)

`GET/POST /api/admin/users`, `DELETE /api/admin/users/{username}` — all
gated by `require_role("admin")`.

`GET /api/admin/users` → `200`:

```json
{"users": [{"username": "admin", "role": "admin", "created_at": "2026-07-03T09:00:00"}]}
```

`POST /api/admin/users` body: `{"username", "password", "role": "admin"|"runner"}`
→ `201` with `{"username", "role"}`; `409` if the username already exists;
`422` if username/password are empty (or fail Pydantic validation — `role`
is a required literal, not optional).

`DELETE /api/admin/users/{username}` → `{"status": "deleted"}`; `400` if
deleting your own account (`username == token.username`), `404` if the user
doesn't exist. See `docs/RUNBOOK.md` §6 for full curl examples.

## 3. Test runs

### 3.1 Start a run

```
POST /api/tests/start
Content-Type: application/json
Authorization: Bearer <token>
```

Body (`TestRunOptions`, `fastapi-server/models.py`) — every field is
optional, defaults shown:

| Field | Type | Default | Validation |
|---|---|---|---|
| `tags` | string | `"@smoke"` | pattern `^[@\w\s\-,()]+$` (Cucumber tag filter, e.g. `"@smoke and not @flaky"`) |
| `retry_count` | int | `0` | `0 <= x <= 10` |
| `browser` | string | `"chrome"` | one of `chrome`, `firefox`, `edge` |
| `parallel` | int | `1` | `1 <= x <= 5` — worker shard count for `single`/`shard` modes |
| `environment` | string | `"staging"` | one of `staging`, `prod`, `dev` |
| `notify_email` | string \| null | `null` | none |
| `version` | string \| null | `null` | none (if omitted, backfilled later from Allure's `environment.properties` when available) |
| `visibility` | string | `"internal"` | one of `internal`, `public` |
| `force` | bool | `false` | **body field, NOT a query parameter** — bypasses the duplicate-run 409 guard |
| `mode` | string | `"single"` | one of `single`, `matrix`, `shard` |
| `workers` | list of `WorkerSpec` \| null | `null` | required non-empty when `mode="matrix"`; each item is `{tags, browser?, environment?}` (`browser`/`environment` fall back to the job-level values when omitted) |
| `features` | string \| null | `null` | comma-separated feature file paths; normally set per-shard-worker internally, not by the caller |

Invalid values are rejected by Pydantic with `422` (see §7). A model
validator additionally rejects: `mode="matrix"` with an empty/missing
`workers` list, and `mode="shard"` combined with `retry_count > 0`.

**Modes** (`_worker_specs` in `server.py`):
- **`single`**: `parallel` identical worker copies, all running the same
  `tags`.
- **`matrix`**: one worker per entry in `workers`, each with its own
  tags/browser/environment.
- **`shard`**: the tag filter's matching scenarios are discovered via a
  Cucumber dry-run (see §3.5), and their feature files are round-robin split
  into `parallel` shards — each worker runs one feature subset via
  `-Dcucumber.features=...`.

Response `200`:

```json
{
  "job_id": "job-a1b2c3d4",
  "workers": [
    {
      "worker_id": "job-a1b2c3d4-w0", "run_id": "test-11223344", "shard": 0,
      "output_dir": "/.../target/allure-results-test-11223344",
      "tags": "@smoke", "browser": "chrome", "environment": "staging", "features": null
    }
  ],
  "runs": ["test-11223344"],
  "status": "started",
  "mode": "serialized_safe",
  "parallel": 1
}
```

- `job_id` groups all shards of one request; `runs`/each `workers[].run_id` is
  the id used for polling, cancelling, and monitoring an individual shard.
- `status` is `"started"` if a `TEST_MAX_CONCURRENCY` slot was free at
  request time (workers were spawned immediately), or `"queued"` if the job
  was admitted straight into `queued` status and will start later via
  `_dispatch_queued` once capacity frees up. **This is a snapshot of the
  admission decision, not a live status feed** — poll §3.2 or subscribe to
  §3.3 for the job's current status.
- `mode` in the response is always the literal string `"serialized_safe"` —
  it does **not** echo the request's `TestRunOptions.mode` (single/matrix/shard).
  Use the request's own `mode` field client-side if you need to know which
  mode you asked for.
- The requester is recorded from the token's `sub` claim (`token.username`,
  including `svc:<name>` for service tokens) and surfaced as `requester` in
  `/api/tests/running` and `/api/tests/jobs` (§3.2).

**Duplicate protection (409):** if a job with the same effective `tags`
(the `matrix` job-level tag is the shards' tags joined with `" | "`) +
`environment` is already `queued` or `running`, the request is rejected
unless the body sets `"force": true`:

```json
{
  "detail": "A run with these tags and environment is already active (job job-a1b2c3d4). Pass force=true to start anyway."
}
```

```bash
curl -X POST "http://localhost:8000/api/tests/start" \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"tags":"@smoke","environment":"staging","force":true}'
```

### 3.2 Monitor via polling

```
GET /api/tests/running   (Authorization: Bearer <token>)
```

Returns jobs whose status is `running` or `queued`:

```json
{
  "running": ["job-a1b2c3d4"],
  "jobs": [
    {
      "job_id": "job-a1b2c3d4",
      "tags": "@smoke",
      "retry_count": 0,
      "parallel": 1,
      "environment": "staging",
      "version": "1.0.0",
      "started_at": "2026-07-03T10:00:00",
      "status": "running",
      "requester": "admin",
      "workers": [
        {"worker_id": "job-a1b2c3d4-w0", "run_id": "test-11223344", "shard": 0, "status": "running", "output_dir": "..."}
      ]
    }
  ],
  "count": 1
}
```

`{"running": [], "jobs": [], "count": 0}` when nothing is active.

```
GET /api/tests/jobs   (Authorization: Bearer <token>)
```

Returns **all** jobs regardless of status, each with the same shape as above
(`status`/`requester` included) plus `ended_at`, and two DuckDB-derived
metrics computed across the job's `run_id`s:

- `flaky_count` — distinct scenarios that failed at least once but passed on
  a later retry within this job's runs.
- `retry_total` — count of `scenario_results` rows with `retry_attempt > 1`
  across this job's runs.

`{"jobs": [], "count": 0}` when there are no jobs yet.

### 3.3 Monitor via WebSocket

Two endpoints, both authenticated via a **query parameter** (not a header):

```
ws://<host>/ws/test-status/{run_id}?token=<jwt>   # one specific worker run
ws://<host>/ws/test-status/live?token=<jwt>       # every run's messages, merged
```

- The token is decoded with `jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])`;
  any decode failure or a missing `sub` claim closes the socket with close
  code `4001`. There is no role check on the WebSocket routes — any valid
  token (any role) can connect.
- **Reconnect behavior** (`websocket_handler.py: ConnectionManager.connect`):
  on connect, the server immediately replays the **last message sent for that
  run_id**, if one exists (`self.last_messages[run_id]`). This applies to
  `/ws/test-status/{run_id}` — a client that connects mid-run or reconnects
  gets the most recent progress/complete/state snapshot without waiting for
  the next event. The `/ws/test-status/live` channel does **not** get its own
  replay (nothing ever broadcasts under the literal run_id `"live"`) — a
  `live` connection sees only messages broadcast from that point forward,
  mirrored from whichever per-run broadcasts happen to fire
  (`ConnectionManager.broadcast` fans every non-`live` message out to `live`
  listeners in addition to the run's own listeners — this mirroring does
  **not** short-circuit even when a run has no direct per-run subscriber).

**Message shapes** (from `execute_test_run` / `_broadcast_state` in `server.py`):

Progress (`type: "progress"`), sent once at start (`pct: 0`) and after every
parsed output line:

```json
{
  "run_id": "test-11223344",
  "total": 12, "passed": 4, "failed": 1, "skipped": 0, "running": 7,
  "scenarios": [{"name": "Login succeeds", "status": "passed"}],
  "output": ["... raw maven/cucumber output lines ..."],
  "pct": 41,
  "type": "progress"
}
```

Complete (`type: "complete"`), sent once when the worker's Maven process
exits:

```json
{
  "run_id": "test-11223344",
  "total": 12, "passed": 11, "failed": 1, "skipped": 0, "running": 0,
  "scenarios": [...], "output": [...],
  "finished": true,
  "type": "complete",
  "exit_code": 0,
  "pct": 100
}
```

State (`type: "state"`), a lifecycle transition frame emitted by
`_broadcast_state` — sent when a job is admitted (`status: "running"` or
`"queued"`, with `job_id` in the extra fields) and again with the run's
final authoritative status once it finishes (`status: "completed"|"failed"|
"cancelled"|"interrupted"`, with `exit_code` in the extra fields):

```json
{"type": "state", "run_id": "test-11223344", "status": "queued", "job_id": "job-a1b2c3d4"}
```
```json
{"type": "state", "run_id": "test-11223344", "status": "completed", "exit_code": 0}
```

A client consuming `/ws/test-status/live` should therefore branch on
`data.type` (`"progress"` / `"complete"` / `"state"`) rather than assuming a
fixed shape — the three frame kinds share only `run_id` + `type`.

### 3.4 Discovery preview (shard mode)

```
GET /api/tests/discovery?tags=@smoke&shards=2   (Authorization: Bearer <token>)
```

Runs a real Cucumber dry-run (`mvn ... -Dcucumber.execution.dry-run=true`,
no browser/steps executed) for `tags`, and shows how the matching scenarios'
feature files would be split into `shards` groups — useful for previewing
`mode: "shard"` before starting a run.

```json
{
  "tags": "@smoke",
  "count": 3,
  "scenarios": [{"name": "Login succeeds", "feature": "features/login.feature", "line": 12}],
  "features": ["features/login.feature", "features/checkout.feature"],
  "shards": [{"features": ["features/login.feature"], "count": 1}, {"features": ["features/checkout.feature"], "count": 1}]
}
```

### 3.5 Cancel

```
POST /api/tests/{run_id}/cancel   (Authorization: Bearer <token>)
```
Cancels the **entire job** that `run_id` belongs to (all sibling workers),
sends `SIGTERM` to the process group of any worker actually running.
Response: `{"status": "cancelled", "run_id": "...", "job_id": "..."}`.
**If `run_id` is unknown, this returns HTTP `200`** with
`{"status": "not_found", "run_id": "..."}` — it does not raise a `404`.

```
POST /api/tests/job/{job_id}/cancel   (Authorization: Bearer <token>)
```
Same effect, addressed by `job_id` directly.
Response: `{"status": "cancelled", "job_id": "..."}`. Works on jobs still in
`queued` status too (they never get a chance to start). **If `job_id` is
unknown, this also returns HTTP `200`** with `{"status": "not_found", "job_id": "..."}`.

## 4. Status machine

```
queued ──────────────► running ──────┬─────► completed
  │                       │          ├─────► failed
  │                       │          └─────► interrupted  (server restarted while running)
  └───────────────────────┴────────────────► cancelled     (either status, via cancel endpoints)
```

| Status | Meaning |
|---|---|
| `queued` | Job/worker rows created; waiting for a `TEST_MAX_CONCURRENCY` slot. Cancelling here just dequeues. |
| `running` | Slot acquired; this worker's Maven process is executing. |
| `completed` | Worker's Maven process exited and result parsing succeeded with no internal error. |
| `failed` | `execute_test_run` hit an exception for this worker, or the underlying Maven process ended in an error state. |
| `cancelled` | A cancel endpoint was called; cancellation is written to the DB **before** the process group receives `SIGTERM`, so a race with the normal completion write can't overwrite `cancelled` back to `completed`/`failed` (final writes are conditioned on `status != 'cancelled'`). |
| `interrupted` | Server process restarted (crash or deploy) while the worker/job was `running` or `queued`; startup recovery marks orphans `interrupted` and best-effort `SIGTERM`s any surviving process group (gated by `RUN_RECOVERY_ON_STARTUP`, default on). |

A job's own status becomes `completed`/`failed` only once **all** of its
worker runs have finished. Two watchdogs can also force a transition out of
`running`: `RUN_STALL_TIMEOUT` (no output for N seconds) and
`RUN_HARD_TIMEOUT` (total wall-clock time exceeded) — see `docs/RUNBOOK.md` §4/§7.

## 5. Results

### 5.1 List runs

```
GET /api/v1/runs?version=<optional>
```

Returns `List[RunManifest]`, newest first, no auth required:

```json
[
  {
    "runId": "test-11223344",
    "timestamp": "2026-07-03T10:05:00",
    "totalScenarios": 12, "passed": 11, "failed": 1, "skipped": 0,
    "duration": "0.0s",
    "version": "1.0.0",
    "environment": "staging",
    "scenarios": [ /* ScenarioResult, see below */ ]
  }
]
```

### 5.2 Run detail

```
GET /api/v1/runs/{run_id}
```

Returns one `RunManifest` (schema above) or `404` if unknown:
`{"detail": "Run 'xyz' not found"}`.

### 5.3 Failures (public)

```
GET /api/v1/runs/{run_id}/failures
```

**No authentication required** — this route has no `verify_token`
dependency. Returns `List[ScenarioResult]` filtered to `status in
("failed", "broken")`.

Resolution order:
1. **Manifest file** (`manifests/{run_id}.json`) — if it exists, failures are
   read straight from its `scenarios` list. This is the common path for runs
   started through this server.
2. **DuckDB fallback** (`_get_run_failures_from_duckdb` in `routes/runs.py`)
   — if no manifest file exists, the run is looked up in the `runs` table,
   then in `scenario_results` (so a run that never got a `runs` row but does
   have scenario rows still counts as known). If found, it selects the
   highest-`retry_attempt` row per `scenario_uid` with `status IN
   ('FAILED','BROKEN')` and maps each to a `ScenarioResult` with `tags: []`,
   `attempts: []`, `attachments: []`, and a single synthetic `steps` entry
   (`{"name": "error", "status": "failed", "errorMessage": <error_message>}`)
   only when `error_message` is non-empty — otherwise `steps: []`. Any DB
   error during the fallback degrades to the same 404 as an unknown run
   rather than a 500 (this route is public).
3. `[]` — the run is known (manifest, or a `runs`/`scenario_results` row
   exists) but has no failing scenarios.
4. `404` — the run_id is not known to either the manifest store or DuckDB:
   `{"detail": "Run 'xyz' not found"}`.

`ScenarioResult` schema (`fastapi-server/models.py`):

```json
{
  "id": "test-11223344-3",
  "name": "Login fails with wrong password",
  "status": "failed",
  "duration": "2.3s",
  "doorsAbsNumber": "DOORS-1234",
  "tags": ["@smoke"],
  "steps": [{"name": "I enter wrong password", "status": "failed", "errorMessage": "AssertionError: ..."}],
  "attachments": [{"name": "screenshot.png", "type": "image/png", "path": "..."}],
  "attempts": [{"status": "failed", "timestamp": "2026-07-03T10:05:00", "errorMessage": "..."}],
  "dependencies": []
}
```

`status` is constrained to `passed|failed|skipped|broken`; `attachments[].type`
to `image/png|video/mp4|text/plain`.

## 6. Agent integration recipe

A minimal end-to-end sequence an AI agent can follow literally:

1. **Log in** (or use a pre-minted service token — skip to step 2 if so):
   ```bash
   TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username":"admin","password":"admin123"}' \
     | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
   ```
2. **Start a run**:
   ```bash
   START=$(curl -s -X POST http://localhost:8000/api/tests/start \
     -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
     -d '{"tags":"@smoke","environment":"staging","parallel":1}')
   RUN_ID=$(echo "$START" | python3 -c 'import sys,json;print(json.load(sys.stdin)["runs"][0])')
   JOB_ID=$(echo "$START" | python3 -c 'import sys,json;print(json.load(sys.stdin)["job_id"])')
   ```
3. **Poll until finished** (or open a WebSocket per §3.3 for live updates):
   ```bash
   until curl -s http://localhost:8000/api/tests/jobs -H "Authorization: Bearer $TOKEN" \
     | python3 -c "import sys,json;j=[x for x in json.load(sys.stdin)['jobs'] if x['job_id']=='$JOB_ID'][0];exit(0 if j['status'] not in ('queued','running') else 1)"
   do sleep 5; done
   ```
4. **Fetch failures** (no token needed):
   ```bash
   curl -s "http://localhost:8000/api/v1/runs/$RUN_ID/failures"
   ```
5. **(Optional) Cancel early** if the agent decides to abort:
   ```bash
   curl -X POST "http://localhost:8000/api/tests/job/$JOB_ID/cancel" -H "Authorization: Bearer $TOKEN"
   ```

## 7. Error handling

| Status | When | Example body |
|---|---|---|
| `401` | Missing/invalid/expired Bearer token on a protected route | `{"detail": "Token expired"}` / `{"detail": "Invalid token"}` / `{"detail": "Invalid credentials"}` (login) |
| `403` | Valid token but wrong role for `require_role(...)` routes (e.g. `runner` calling `/api/admin/users`) | `{"detail": "Requires role in ['admin']"}` |
| `404` | Unknown `run_id` on `GET /api/v1/runs/{run_id}` or `.../failures`; unknown username on `DELETE /api/admin/users/{username}` | `{"detail": "Run 'xyz' not found"}` / `{"detail": "User 'xyz' not found"}` |
| `409` | Duplicate `tags`+`environment` job already queued/running without `"force": true` in the body; username already exists on user creation | `{"detail": "A run with these tags and environment is already active (job job-a1b2c3d4). Pass force=true to start anyway."}` |
| `422` | Request body fails Pydantic validation (e.g. `parallel: 9`, bad `tags` pattern, bad enum value, `mode:"matrix"` with no `workers`) | `{"detail": [{"type": "less_than_equal", "loc": ["body", "parallel"], "msg": "Input should be less than or equal to 5", "input": 9, ...}]}` (standard FastAPI/Pydantic validation error array) |

**Note:** unlike a typical REST API, `POST /api/tests/{run_id}/cancel` and
`POST /api/tests/job/{job_id}/cancel` do **not** raise `404` for an unknown
id — they return HTTP `200` with `{"status": "not_found", ...}` (see §3.5).
Check the `status` field in the response body, not the HTTP status code, for
these two routes.

## 8. Other endpoints (not detailed here)

The server also exposes triage workflow (`/api/triage/*`), Jira bug creation
(`/api/v1/bugs/*`, `/api/v1/runs/{run_id}/scenarios/{scenario_id}/jira`),
DOORS DXL execution (`/api/doors/*`), email sending (`/api/email/*`),
public report sharing (`/api/reports/generate-share`,
`/api/public/reports/*`, `/public/reports*`), CSV export (`/api/csv/*`),
scenario history/matrix (`/api/scenario-history*`, `/api/scenario-matrix`),
run/version admin (`/api/admin/sync-runs`, `/api/admin/runs*`,
`/api/versions`, `/api/dashboard/metrics`), pipeline control
(`/api/pipeline/run`, `/api/pipeline/status/{run_id}`), and HTML page routes
(`/`, `/dashboard`, `/admin`, `/reports/*`). These are engineer-facing
UI/integration features outside this API's scope for agent consumption —
read `fastapi-server/routes/*.py` directly if needed.
