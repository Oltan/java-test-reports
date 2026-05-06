# FastAPI Operator Runbook

This runbook is for operators who run tests, triage failures, and publish safe report links.

## Public vs Engineer

Engineer routes require a bearer token from `POST /api/v1/auth/login`. Use them only from trusted operator consoles.

Engineer HTML routes:

1. `/dashboard`, full dashboard.
2. `/admin`, operator page.
3. `/reports/merge`, merged report view.
4. `/reports/{run_id}`, internal report detail unless the run visibility is public.
5. `/reports/{run_id}/scenario/{scenario_id}`, scenario detail.
6. `/reports/{run_id}/triage`, triage page.
7. `/reports/{artifact_path:path}`, protected artifact download under the manifests directory.

Engineer API routes:

1. `/api/tests/start`, start a test job.
2. `/api/tests/running`, list running jobs and workers.
3. `/api/tests/jobs`, list job history and worker details.
4. `/api/tests/{run_id}/cancel` and `/api/tests/job/{job_id}/cancel`, cancel work.
5. `/api/pipeline/run` and `/api/pipeline/status/{run_id}`, pipeline controls.
6. `/api/v1/runs`, `/api/v1/runs/{run_id}`, `/api/v1/runs/{run_id}/failures`, `/api/v1/runs/{run_id}/bug-status`, run data.
7. `/api/triage/{run_id}` plus scenario Jira, link, and override routes, failure triage.
8. `/api/reports/generate-share`, create a public snapshot.
9. `/api/doors/run`, `/api/doors/share/{share_id}`, DOORS actions.
10. `/api/email/send`, `/api/email/share/{share_id}`, email actions.
11. `/api/admin/sync-runs`, `/api/versions`, `/api/dashboard/metrics`, admin and dashboard support.

Public routes do not require a bearer token:

1. `/`, basic landing dashboard.
2. `/api/v1/auth/login`, token issue route.
3. `/public/reports/{share_id}`, public HTML snapshot for recipients.
4. `/api/public/reports/{share_id}`, sanitized snapshot JSON for the same share.
5. `/static/*`, static assets.

Legacy bug lookup routes, `/api/v1/bugs` and `/api/v1/bugs/{doors_number}`, are also open in the current server. Treat them as internal compatibility routes. Do not use them as the customer sharing path.

## Parallel and Retry

Test jobs start through `POST /api/tests/start` with `TestRunOptions`.

Allowed options:

1. `tags`, a Cucumber tag such as `@smoke`.
2. `retry_count`, from `0` to `10`. When greater than zero, the server passes `-Dretry.count=<value>` to Maven.
3. `browser`, one of `chrome`, `firefox`, or `edge`.
4. `parallel`, from `1` to `5`.
5. `environment`, one of `dev`, `staging`, or `prod`.
6. `version`, optional release label.
7. `visibility`, `internal` or `public`.

The current parallel mode is `serialized_safe` v1. The server creates one worker record per requested shard, with fields such as `worker_id`, `run_id`, `shard`, `status`, and `output_dir`. For `parallel > 1`, workers are still run one after another. This protects shared browser, Maven, and Allure output state while giving operators a stable worker display.

Use these routes for worker display:

1. `GET /api/tests/running`, current running jobs.
2. `GET /api/tests/jobs`, history, worker status, retry totals, and flaky counts.

Example start request:

```bash
TOKEN="<bearer_token>"

curl -X POST "http://localhost:8000/api/tests/start" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "tags": "@smoke",
    "retry_count": 1,
    "browser": "chrome",
    "parallel": 2,
    "environment": "staging",
    "version": "2026.05.03",
    "visibility": "internal"
  }'
```

## Triage

Triage is required before a failed or broken scenario can be shared publicly.

Use `GET /api/triage/{run_id}` to see failed scenarios, DOORS numbers, existing Jira keys, retry attempts, flaky flags, decisions, actors, reasons, and timestamps.

Accepted triage outcomes for public sharing:

1. `jira_created`, created from the server.
2. `jira_linked`, linked to an existing Jira issue.
3. `accepted_pass`, operator override.
4. `accepted_skip`, operator override.

Jira create flow:

1. Call `POST /api/triage/{run_id}/scenarios/{scenario_id}/jira`.
2. The server creates a Jira issue from the scenario failure, stores it in `jira_mappings`, and records `jira_created` in `triage_decisions`.
3. If the scenario already has a Jira mapping, the existing key is returned.

Jira link flow:

1. Call `POST /api/triage/{run_id}/scenarios/{scenario_id}/link-jira` with a non empty `jira_key`.
2. The server stores the mapping and records `jira_linked`.

Override flow:

1. Call `POST /api/triage/{run_id}/scenarios/{scenario_id}/override`.
2. `decision` must be `accepted_pass` or `accepted_skip`.
3. `reason` is required and cannot be blank.
4. The server writes an audit row to `override_audit`, then writes the current decision to `triage_decisions` with the actor from the token.

Example override:

```bash
curl -X POST "http://localhost:8000/api/triage/<run_id>/scenarios/<scenario_id>/override" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"decision":"accepted_skip","reason":"Known lab outage confirmed by operator"}'
```

## Share

Public shares are snapshots. They are not live internal reports.

Create a share with `POST /api/reports/generate-share`. Send `scenario_ids` for the exact scenarios that recipients may see. The route is engineer only.

Blocker enforcement:

1. If a selected failed or broken scenario has no triage decision, share creation returns `409` with blockers.
2. If the decision is not `jira_created`, `jira_linked`, `accepted_pass`, or `accepted_skip`, share creation returns `409` with blockers.
3. Passed and skipped scenarios can be selected without Jira triage.

Public redaction:

1. The snapshot is built through `PublicReportSnapshot.from_internal`.
2. Public scenario entries contain name and status only.
3. Public summary contains total scenarios, passed, failed, skipped, and generated timestamp.
4. Internal identifiers, Jira keys, DOORS numbers, paths, logs, screenshots, videos, and error messages are not included in the public HTML route.

Successful share creation returns:

```json
{
  "share_id": "<share_id>",
  "url": "/public/reports/<share_id>"
}
```

Give recipients only `/public/reports/{share_id}`. Use `/api/public/reports/{share_id}` only when an approved public client needs sanitized JSON.

## DOORS

DOORS actions are engineer only.

Routes:

1. `POST /api/doors/run`, runs a supplied DXL script when DOORS is available.
2. `POST /api/doors/share/{share_id}`, loads the public snapshot, builds a DXL export from its scenario names, and runs it when DOORS is available.

If DOORS is not installed, the server returns `{"status":"unavailable","message":"DOORS not installed"}`. Treat that as a skipped integration, not as a report failure.

Use the share export route after public share creation, not before triage. The DXL payload must be based on the redacted public snapshot.

## Email

Email actions are engineer only.

Routes:

1. `POST /api/email/send?to=<recipient>&run_id=<run_id>`, sends an internal report link to `/reports/{run_id}`.
2. `POST /api/email/share/{share_id}?to=<recipient>`, sends the public share summary and sets `dashboard_url` to `/public/reports/{share_id}`.

Use the share email route for external recipients. Confirm the public share first, then send email with the share link. Do not send internal report URLs to public recipients.

## Commands

Start the FastAPI server:

```bash
cd fastapi-server
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Get a bearer token with operator supplied credentials:

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"<operator_user>","password":"<operator_password>"}'
```

Run Maven tests directly:

```bash
export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH"
mvn -pl test-core test -Dcucumber.filter.tags="@smoke"
```

Run the FastAPI test suite:

```bash
cd fastapi-server
python3 -m pytest tests/ -v
```
