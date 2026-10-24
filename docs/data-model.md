# Data Model & Indexes (Phase 3)

Primary database: PostgreSQL 16 (SQLite is supported for tests/local dev only). Schema is managed by Alembic (`backend/migrations`); a test asserts the migration matches the ORM models.

## Tables

| Table | Primary key | Purpose |
|---|---|---|
| `projects` | `id` | Tenant‑scoped project (`tenant_id` defaults to `default`; single‑tenant MVP, see D‑008) |
| `agents` | `(project_id, id)` | Registered/auto‑registered agents |
| `api_keys` | `id` | Hashed project API keys (`key_prefix` unique, `key_hash` HMAC‑SHA256, `scopes`, `revoked_at`) |
| `runs` | `(project_id, run_id)` | Searchable run record (fields per `telemetry-schema.md` §4) + `start_confirmed` flag |
| `events` | `(project_id, event_id)` | Raw accepted events; `(project_id, event_id)` is the idempotency key |

`project_id` leads every tenant‑owned primary key, so identifiers submitted by different projects can never collide or overwrite each other, and every query filters on it.

Run record additions/deviations from the Phase 1 schema document:

* `llm_call_count`, `tool_call_count`, token totals are `NOT NULL DEFAULT 0` (they are aggregates).
* `sdk_version` is `'unknown'` unless the SDK supplies it (the Phase 2 SDK does not send it yet).
* `trace_id` / `root_span_id` are derived deterministically for placeholder runs until `run_started` supplies real ones.
* `start_confirmed` is internal bookkeeping for out‑of‑order ingestion.

## Indexes and the queries they serve

| Index | Columns | Serves |
|---|---|---|
| `ix_runs_project_started` | `(project_id, started_at)` | Default run list (newest first) and time‑range filters |
| `ix_runs_project_agent_started` | `(project_id, agent_id, started_at)` | Runs by agent; per‑agent stats |
| `ix_runs_project_status_started` | `(project_id, status, started_at)` | Runs by status |
| `ix_runs_project_env_started` | `(project_id, environment, started_at)` | Runs by environment |
| `ix_runs_project_error` | `(project_id, status, error_type)` | Error summary `GROUP BY` |
| `ix_events_project_run_ts` | `(project_id, run_id, timestamp)` | Fetch one run's events in order |
| `uq_api_keys_prefix` | `(key_prefix)` unique | API‑key lookup during authentication |

Primary keys cover run/event/agent point lookups. Indexes were chosen from the query patterns in `backend/marg_backend/queries.py`; no speculative indexes were added. `EXPLAIN` analysis on PostgreSQL with realistic volumes is deferred to Phase 9 (performance hardening).

## Retention

Not implemented in Phase 3. Retention (default 90 days for runs/events per `architecture.md` §6) is a later‑phase concern; nothing deletes data automatically.
