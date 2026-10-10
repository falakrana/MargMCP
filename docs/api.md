# AgentOps MCP — Ingestion & Query API (Phase 3)

Base URL (local): `http://localhost:8000`. Interactive OpenAPI docs: `/docs`, schema: `/openapi.json`.

All timestamps are ISO‑8601 UTC. All errors use one envelope:

```json
{"error": {"code": "machine_code", "message": "Human text", "details": []}}
```

`details` appears only for validation errors and lists `loc`, `msg`, `type` — never the submitted values.

## Authentication

| Caller | Credential | Header |
|---|---|---|
| SDK / project service | Project API key (`aop_<prefix>_<secret>`) with scope `ingest` and/or `read` | `Authorization: Bearer <key>` |
| Operator (registration only) | `AGENTOPS_ADMIN_TOKEN` | `Authorization: Bearer <token>` |

* Keys belong to exactly one project. Using a key against another project returns `403 project_access_denied`.
* Keys are stored as HMAC‑SHA256 hashes (keyed with `AGENTOPS_SECRET_KEY`); the plaintext is shown once on creation and never logged.
* If `AGENTOPS_ADMIN_TOKEN` is unset the admin API returns `503 admin_disabled`.

## Registration (admin)

```bash
# 1. Create a project
curl -X POST localhost:8000/v1/admin/projects -H "Authorization: Bearer $ADMIN" \
  -H 'Content-Type: application/json' -d '{"name": "My Project"}'
# -> 201 {"id": "<project_id>", "tenant_id": "default", "name": "My Project", "created_at": "...", "agent_count": 0}

# 2. (optional) Pre-register an agent. Unknown agents are auto-registered on first ingest
#    unless AGENTOPS_AUTO_REGISTER_AGENTS=false.
curl -X POST localhost:8000/v1/admin/projects/$PID/agents -H "Authorization: Bearer $ADMIN" \
  -H 'Content-Type: application/json' -d '{"name": "support-bot", "agent_id": "support-bot"}'

# 3. Create an API key (scopes: ingest, read)
curl -X POST localhost:8000/v1/admin/projects/$PID/api-keys -H "Authorization: Bearer $ADMIN" \
  -H 'Content-Type: application/json' -d '{"name": "prod-sdk", "scopes": ["ingest", "read"]}'
# -> 201 {"id": 1, "project_id": "...", "name": "prod-sdk", "scopes": ["ingest","read"], "api_key": "aop_..."}
```

## Ingestion — `POST /v1/telemetry/events`  (scope `ingest`)

Request (schema v1.0, see `telemetry-schema.md`):

```json
{
  "schema_version": "1.0",
  "project_id": "<project_id>",
  "batch": [
    {
      "schema_version": "1.0",
      "event_id": "9b2f…",
      "agent_id": "support-bot",
      "run_id": "run-123",
      "event_type": "run_started",
      "timestamp": "2026-10-08T11:30:00Z",
      "environment": "production",
      "data": {"trace_id": "<32 hex>", "root_span_id": "<16 hex>", "metadata": {"team": "ml"}}
    }
  ]
}
```

Response `202 Accepted`:

```json
{"accepted": 1, "duplicates": 0, "rejected": []}
```

`rejected` lists events refused individually (they are not stored; the rest of the batch is):

```json
{"accepted": 0, "duplicates": 0,
 "rejected": [{"index": 0, "event_id": "9b2f…", "code": "timestamp_out_of_range", "message": "…"}]}
```

### Validation rules

| Rule | Limit / behavior |
|---|---|
| Body size | ≤ 1 MiB (`AGENTOPS_MAX_PAYLOAD_BYTES`) → `413` |
| Batch size | 1–100 events → `422 batch_too_large` / validation error |
| IDs (`event_id`, `agent_id`, `run_id`, `project_id`) | `^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$` (UUIDs satisfy this; the SDK's `"default"` agent id is allowed) |
| `timestamp` | ISO‑8601 **string with UTC offset**; ±24 h of server time else per‑event `timestamp_out_of_range` |
| `event_type` | `run_started`, `run_completed`, `run_failed`, `run_cancelled`, `llm_call_{started,completed,failed}`, `tool_call_{started,completed,failed}`, `custom_event`, `output_summary` (SDK extension) |
| `environment` | `development`, `staging`, `production` |
| `data` | ≤ 16 KiB; only allow‑listed keys are stored (others dropped); forbidden keys (`prompt`, `response`, `input`, `output`, `llm.prompt`, `tool.input`, `api_key`, `secret`, …) reject the event |
| `data.trace_id` / `root_span_id` | 32 / 16 lowercase hex |
| `data.metadata` | ≤ 10 keys, scalar values ≤ 256 chars |
| token counts | non‑negative integers |
| `error_summary` | truncated to 1024 chars |

### Idempotency & lifecycle

* `(project_id, event_id)` is the idempotency key. Retries return `duplicates` and change nothing (run counters are not double counted).
* Events may arrive out of order. A run first seen via a non‑start event is a placeholder with status `unknown`; `run_started` later confirms start time, trace IDs and `running` status. Duration is computed once both start and end are known.
* Terminal status (`run_completed`→`success`, `run_failed`→`error`, `run_cancelled`→`cancelled`) is set once. A *different* terminal event afterwards is rejected with `invalid_status_transition`; the same terminal event again is accepted as a no‑op. Late non‑terminal events are still recorded.
* A `run_id` that already belongs to another agent is rejected with `agent_mismatch`.
* The batch is one database transaction: a storage failure returns `503 database_unavailable` and nothing from the batch is persisted, so retrying the whole batch is safe.

## Query (scope `read`; path `project_id` must match the key's project)

| Endpoint | Description |
|---|---|
| `GET /v1/projects/{pid}` | Project metadata + agent count |
| `GET /v1/projects/{pid}/agents` | Agents with `run_count`, `last_run_at` |
| `GET /v1/projects/{pid}/agents/{agent_id}` | One agent |
| `GET /v1/projects/{pid}/runs` | Filter + paginate runs |
| `GET /v1/projects/{pid}/runs/{run_id}` | Run + ordered events (`max_events`, default 500, max 1000) |
| `GET /v1/projects/{pid}/errors/summary` | Failed runs grouped by agent + error type |

`/runs` query params: `agent_id`, `status` (`running|success|error|cancelled|unknown`), `environment`, `started_after` (inclusive), `started_before` (exclusive), `page` (≥1), `page_size` (1–100, default 25). Naive datetimes are treated as UTC. Results are newest first. Note: `+` in an offset must be URL‑encoded (`%2B`); prefer `Z`.

```bash
curl -H "Authorization: Bearer $KEY" \
  "localhost:8000/v1/projects/$PID/runs?status=error&started_after=2026-10-08T00:00:00Z&page_size=10"
```

```json
{"items": [{"run_id": "run-123", "agent_id": "support-bot", "project_id": "…", "trace_id": "…",
            "root_span_id": "…", "environment": "production", "status": "error",
            "started_at": "2026-10-08T11:30:00Z", "ended_at": "2026-10-08T11:30:03Z", "duration_ms": 3000,
            "error_type": "TimeoutError", "error_summary": "timed out", "llm_call_count": 1,
            "tool_call_count": 1, "total_tokens": 15, "metadata": null, "...": "..."}],
 "total": 1, "page": 1, "page_size": 10}
```

## Health

* `GET /health/live` → `200 {"status":"alive"}`
* `GET /health/ready` → `200 {"status":"ready"}` or `503 {"error":{"code":"not_ready",…}}` — checks the database only and reveals no connection details.

## Error codes

| HTTP | Code | Meaning |
|---|---|---|
| 400 | `invalid_json` | Body is not JSON |
| 401 | `unauthorized` | Missing/invalid/revoked key or admin token |
| 403 | `insufficient_scope` | Key lacks `ingest`/`read` |
| 403 | `project_access_denied` | Key is not valid for that project |
| 404 | `not_found` | Resource missing (or belongs to another project) |
| 405 | `method_not_allowed` | |
| 409 | `already_exists` | Duplicate project/agent id |
| 413 | `payload_too_large` | Body over limit |
| 422 | `validation_error` | Schema/field validation (see `details`) |
| 422 | `unsupported_schema_version` | `schema_version` not `"1.0"` |
| 422 | `batch_too_large` | More than 100 events |
| 422 | `invalid_time_range` | `started_after >= started_before` |
| 500 | `internal_error` | Unexpected error (no internals exposed) |
| 503 | `database_unavailable` | Storage failure; retry |
| 503 | `not_ready` | Readiness failed |
| 503 | `admin_disabled` | Admin token not configured |

Per‑event rejection codes (inside a `202` response): `timestamp_out_of_range`, `forbidden_attribute`, `data_too_large`, `invalid_metadata`, `invalid_attributes`, `invalid_trace_id`, `invalid_span_id`, `invalid_token_count`, `invalid_status_transition`, `agent_mismatch`, `unknown_agent`, `project_mismatch`.
