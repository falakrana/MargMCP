# AgentOps MCP — Progress Log

> This file is the chronological work log. Append new entries; do not rewrite history to make progress appear better. Only the human owner can approve a phase.

## Project snapshot

- **Project:** AgentOps MCP
- **Current phase:** Phase 4 — Metrics, Prometheus, and Trace Export Pipeline
- **Current status:** READY_FOR_REVIEW
- **Last human-approved phase:** Phase 3
- **Next permitted action:** Await human owner review and explicit approval of Phase 4 before beginning Phase 5.
- **Source of detailed requirements:** `implementation.md` plus approved PRD/SRS and architecture decisions.

## Phase checklist

Use only these statuses: `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, `READY_FOR_REVIEW`, `APPROVED`.

| Phase | Name | Status | Approval / notes |
|---|---|---|---|
| 1 | Repository Discovery, Architecture, and Implementation Plan | APPROVED | Approved by owner |
| 2 | Core SDK and First Instrumentation Adapter | APPROVED | Approved by owner |
| 3 | Ingestion API, Persistence, and Query Services | APPROVED | Approved by owner |
| 4 | Metrics, Prometheus, and Trace Export Pipeline | READY_FOR_REVIEW | Implementation complete, 134 backend tests passing, awaiting human approval |
| 5 | Trace Details and Run History | NOT_STARTED | Requires explicit approval of Phase 4 |
| 6 | Monitoring Dashboard | NOT_STARTED | Requires explicit approval of Phase 5 |
| 7 | MCP Server and Read-Only Monitoring Tools | NOT_STARTED | Requires explicit approval of Phase 6 |
| 8 | AI Diagnostic Assistant | NOT_STARTED | Requires explicit approval of Phase 7 |
| 9 | Security, Reliability, and Performance Hardening | NOT_STARTED | Requires explicit approval of Phase 8 |
| 10 | Deployment, End-to-End Pilot, and Release Readiness | NOT_STARTED | Requires explicit approval of Phase 9 |

## Decision and blocker register

| Date | Type | Description | Owner / next action | Status |
|---|---|---|---|---|
| TBD | Assumption | Initial SDK target, database, trace backend, deployment target, retention, and SLOs must be checked against existing PRD/SRS and repository decisions. | Coding agent documents findings during Phase 1; human resolves material decisions. | OPEN |

## Work-session history

### Initial setup — 2026-10-03
- Created this progress-log template and the persistent coding-agent instructions.
- No repository implementation, tests, or deployment have been performed by creating these templates.
- Phase status remains `NOT_STARTED`; no phase has been approved.
- Next action: the coding agent should inspect the actual repository and execute Phase 1 only.

### 2026-10-04 — Phase 1: Repository Discovery, Architecture, and Implementation Plan
- **Status at start:** `NOT_STARTED`
- **Work performed:**
  - Inspected repository: 4 planning files (AGENTS.md, PRD.md, implementation.md, PROGRESS.md), no code, no git history
  - Initialized git repository
  - Created `.gitignore` and `.env.example`
  - Wrote `docs/architecture.md`: full component diagram, trust boundaries, data flow, storage matrix, proposed repo structure
  - Wrote `docs/telemetry-schema.md`: schema v1 with event types, run record, trace span, span attributes, ingestion payload format, metrics definitions, MCP tool contracts
  - Wrote `docs/assumptions-and-decisions.md`: 10 decisions, 8 assumptions, 5 open questions
  - Wrote `docs/implementation-plan.md`: phase checklists with testable criteria for all 10 phases
  - Wrote `docs/testing-strategy.md`: 5-tier testing approach (unit, integration, contract, security, performance)
  - Created `IMPLEMENTATION_STATUS.md`
  - Created `README.md`
  - Updated `PROGRESS.md`
- **Files added:**
  - `.gitignore`, `.env.example`, `README.md`, `IMPLEMENTATION_STATUS.md`
  - `docs/architecture.md`, `docs/telemetry-schema.md`, `docs/implementation-plan.md`, `docs/testing-strategy.md`, `docs/assumptions-and-decisions.md`
- **Files modified:**
  - `PROGRESS.md` (appended session entry, updated phase status)
- **Commands run and actual results:**
  - `git status` — confirmed no git repo existed; EXIT 1
  - `git init` — initialized empty repo; EXIT 0
  - `Get-ChildItem -Recurse` — confirmed 4 files only; EXIT 0
- **Tests added/updated:** N/A (no code to test in Phase 1)
- **Acceptance criteria evidence:**
  - Repository state documented: ✅ (this entry)
  - Architecture matches product scope: ✅ (`docs/architecture.md` covers all PRD components)
  - Data flow and responsibilities understandable: ✅ (Architecture §2, §5, §6)
  - Assumptions visible: ✅ (`docs/assumptions-and-decisions.md`)
  - Phase plan has testable exit criteria: ✅ (`docs/implementation-plan.md`)
  - No application behavior changed: ✅ (no code existed)
- **Decisions/assumptions:**
  - PostgreSQL chosen over MongoDB (better relational querying for run history; see D-003)
  - Single-tenant MVP with tenant_id built into schemas from day one (see D-008)
  - Generic Python decorator as first adapter, not framework-specific (see A-001)
- **Blockers/known limitations:**
  - No CI pipeline yet (Phase 10)
  - Open questions Q-001 through Q-005 can be deferred to relevant phases
- **Human verification steps:**
  - Review `docs/architecture.md` — is the component structure correct?
  - Review `docs/telemetry-schema.md` — are the event types and fields sufficient?
  - Review `docs/assumptions-and-decisions.md` — any decisions to override?
  - Review proposed repo structure in architecture doc — acceptable layout?
  - Review `.env.example` — any missing config variables?
- **Status at end:** `READY_FOR_REVIEW`
- **Human approval:** None — awaiting review.
- **Next permitted action:** Wait for explicit human approval before beginning Phase 2.

### 2026-10-04 — Phase 2: Core SDK and First Instrumentation Adapter
- **Status at start:** `NOT_STARTED`
- **Work performed:**
  - Designed the `agentops-sdk` Python package structure in `sdk/`.
  - Implemented `AgentOpsConfig` leveraging environment variables for configuration.
  - Implemented `TelemetryEvent` canonical models in `events.py` via Pydantic.
  - Added contextvars for propagation in `context.py`.
  - Created exporter abstraction `BaseExporter`.
  - Implemented `HttpExporter` for sending telemetry payloads to the ingestion API.
  - Implemented `AsyncBatchProcessor` to handle non-blocking, background queued batch flushes with proper shutdown logic.
  - Developed the `AgentOps` main client and `Run` context manager with automatic exception handling and metadata redaction hooks.
  - Created generic adapter `@observe_agent` in `adapters/decorator.py`.
  - Added a test suite with 100% mocked backend integration, validating lifecycle events, failure resilience, and payload redaction.
  - Fixed a shutdown bug in the batch processor to ensure the event queue flushes completely on application exit.
  - Provided `examples/simple_agent.py` to showcase usage.
- **Files added/modified:**
  - `sdk/agentops_sdk/client.py`, `config.py`, `context.py`, `events.py`, `redaction.py`, `adapters/decorator.py`, `exporters/base.py`, `exporters/batch.py`, `exporters/http.py`.
  - `sdk/tests/test_sdk.py`, `sdk/pyproject.toml`, `sdk/README.md`.
  - `examples/simple_agent.py`.
- **Commands run and actual results:**
  - `python -m pip install -e ".[dev]"; pytest` — PASS (3 tests, 86% coverage, SDK components working).
  - `git commit` — PASS.
- **Tests added/updated:** 
  - `test_successful_run_lifecycle`, `test_failed_run_lifecycle`, `test_telemetry_failure_does_not_crash_agent` added to `tests/test_sdk.py`.
- **Acceptance criteria evidence:**
  - Python agent instrumented: ✅ (Tested via example & unit tests)
  - Telemetry payload normalized: ✅ (Validated through `TelemetryEvent` model)
  - Exceptions not hidden: ✅ (`test_failed_run_lifecycle`)
  - Telemetry failure bounds: ✅ (`test_telemetry_failure_does_not_crash_agent`)
- **Decisions/assumptions:**
  - Used `pytest` and `responses` to mock out the backend API.
  - Added simple `.env` style configuration through Pydantic fields.
- **Blockers/known limitations:** None.
- **Human verification steps:**
  - Review the SDK API in `sdk/README.md` and `examples/simple_agent.py`.
  - Verify that redaction defaults correctly skip `prompt`/`secret` payloads.
  - Review the background batch processor `AsyncBatchProcessor` behavior.
- **Status at end:** `READY_FOR_REVIEW`
- **Human approval:** Approved by owner ("IMPLEMENT IT." authorized Phase 3).
- **Next permitted action:** Execute Phase 3.

### 2026-10-08 — Phase 3: Ingestion API, Persistence, and Query Services
- **Status at start:** `NOT_STARTED`
- **Work performed:**
  - Implemented FastAPI backend package `backend/agentops_backend/` with modular layout (`main.py`, `config.py`, `models.py`, `schemas.py`, `auth.py`, `db.py`, `ingestion.py`, `queries.py`, `registry.py`, `errors.py`, `routes.py`, `seed.py`).
  - Implemented secure API-key authentication with HMAC-SHA256 hashed keys, scope verification (`ingest`, `read`), and admin token bootstrapping (`AGENTOPS_ADMIN_TOKEN`). Keys are shown once at creation and never logged or exposed via endpoints.
  - Implemented project/tenant boundary enforcement: all primary keys and query layers scope strictly by `project_id`.
  - Implemented telemetry ingestion endpoint (`POST /v1/telemetry/events`) with schema v1.0 validation, strict type/timestamp parsing, payload limits (1 MiB default, 100 max events per batch), payload size checks, forbidden attribute screening, and per-event error reporting.
  - Implemented idempotent persistence with `(project_id, event_id)` idempotency key, out-of-order event convergence, run duration calculation, and run state machine enforcing single-terminal transitions.
  - Implemented query endpoints: project metadata (`GET /v1/projects/{pid}`), agent listing & details (`GET /v1/projects/{pid}/agents`), run history with pagination, status/agent/environment filters and half-open time boundaries (`GET /v1/projects/{pid}/runs`), run details with chronological events (`GET /v1/projects/{pid}/runs/{run_id}`), and error summary aggregates (`GET /v1/projects/{pid}/errors/summary`).
  - Implemented health and readiness endpoints (`GET /health/live`, `GET /health/ready`) with zero secret/driver exposure.
  - Configured database indexes for query access patterns and created Alembic migrations (`backend/migrations/`).
  - Added synthetic seed dataset generation tool (`agentops_backend.seed`), clearly marked with `synthetic=true`.
  - Created Dockerfile (`backend/Dockerfile`), local compose stack (`infra/docker-compose.yml`), and documentation (`docs/api.md`, `docs/data-model.md`, `backend/README.md`).
  - Added comprehensive test suite (89 tests covering auth, ingestion, lifecycle, idempotency, queries, error handling, reliability, contracts, and migrations) reaching 97% code coverage.
- **Files added/modified:**
  - Added: `backend/pyproject.toml`, `backend/alembic.ini`, `backend/Dockerfile`, `backend/README.md`
  - Added: `backend/agentops_backend/__init__.py`, `config.py`, `db.py`, `errors.py`, `auth.py`, `models.py`, `schemas.py`, `ingestion.py`, `queries.py`, `registry.py`, `routes.py`, `main.py`, `seed.py`
  - Added: `backend/migrations/env.py`, `backend/migrations/script.py.mako`, `backend/migrations/versions/0001_initial_schema.py`
  - Added: `backend/tests/__init__.py`, `conftest.py`, `test_auth.py`, `test_contract.py`, `test_ingestion.py`, `test_query.py`, `test_reliability.py`, `test_seed.py`
  - Added: `infra/docker-compose.yml`, `docs/api.md`, `docs/data-model.md`
  - Modified: `.env.example`, `.gitignore`, `PROGRESS.md`, `IMPLEMENTATION_STATUS.md`
- **Commands run and actual results:**
  - `python -m venv .venv; pip install -e ".[dev]"` — PASS (backend dependencies installed in dedicated venv)
  - `pytest --cov=agentops_backend --cov-report=term-missing` (backend) — PASS (89 tests passed, 97% coverage)
  - `pytest` (sdk) — PASS (3 tests passed, 86% coverage)
  - `alembic upgrade head` — PASS (migrations applied successfully)
  - `python -m agentops_backend.seed` — PASS (synthetic demo project, agents, and runs generated)
  - `uvicorn agentops_backend.main:app_factory --factory` — PASS (started live server, verified `/health/live` and `/health/ready`)
- **Tests added/updated:**
  - `tests/test_auth.py`: 17 tests (auth validation, hashing, scopes, token tampering, cross-tenant isolation, admin token)
  - `tests/test_ingestion.py`: 40 tests (payload sizes, schema versioning, field validations, idempotency, duplicates, out-of-order events, lifecycle transitions, agent auto-registration)
  - `tests/test_query.py`: 15 tests (run filtering, pagination, time range boundaries, agent stats, error summaries)
  - `tests/test_reliability.py`: 11 tests (transaction rollback on failure, structured 503 errors, data persistence across restart, health checks, Alembic vs ORM model sync)
  - `tests/test_contract.py`: 5 tests (OpenAPI endpoints, run schema fields, error envelope consistency, real SDK payload wire-compatibility)
  - `tests/test_seed.py`: 1 test (synthetic data seeding and idempotency)
- **Acceptance criteria evidence:**
  - SDK payload received, validated, and persisted: ✅ (`test_sdk_wire_payload_is_accepted`, `test_valid_run_is_persisted_and_retrievable`)
  - Runs queryable by project, agent, status, time range: ✅ (`test_filter_by_agent_status_environment`, `test_pagination`, `test_time_range_boundaries_are_half_open`)
  - Duplicate retries do not corrupt history: ✅ (`test_duplicate_events_do_not_corrupt_history`, `test_same_terminal_status_repeat_is_idempotent`)
  - Unauthorized users cannot read or write another project's telemetry: ✅ (`test_cannot_ingest_into_another_project`, `test_cannot_read_another_projects_telemetry`)
  - API documentation and automated tests available: ✅ (`docs/api.md`, `docs/data-model.md`, 89 automated tests)
- **Decisions/assumptions:**
  - Project ID acts as the leading column in composite primary keys (`(project_id, run_id)`, `(project_id, event_id)`) to guarantee hard data isolation.
  - SQLite supported for developer ergonomics and test suites, with PostgreSQL target production deployment.
  - Single transaction per ingestion batch guarantees all-or-nothing atomicity upon transient storage failures.
- **Blockers/known limitations:**
  - Docker CLI was not available in the local Windows environment; PostgreSQL verification relied on SQLite test run and strict Alembic migration contract tests.
- **Human verification steps:**
  - Follow the manual verification checklist below.
- **Status at end:** `APPROVED`
- **Human approval:** Approved by owner ("So as phase 3 is complete. Can you commit accordingly?").
- **Next permitted action:** Phase 3 approved; commit Phase 3 implementation and await authorization to begin Phase 4.

### 2026-10-11 — Phase 4: Metrics, Prometheus, and Trace Export Pipeline
- **Status at start:** `APPROVED` (Phase 3 approved by human owner; authorization "Start Phase 4" given).
- **Work performed:**
  - Designed and implemented Prometheus metrics module (`backend/agentops_backend/metrics.py`) using an isolated `CollectorRegistry` instance to prevent global collector leakage across tests and processes.
  - Implemented core time-series metrics per `docs/telemetry-schema.md`: `agentops_runs_total`, `agentops_run_duration_seconds`, `agentops_llm_calls_total`, `agentops_llm_call_duration_seconds`, `agentops_tool_calls_total`, `agentops_tool_call_duration_seconds`, `agentops_tokens_total`, `agentops_ingestion_requests_total`, `agentops_ingestion_latency_seconds`, `agentops_events_total`, `agentops_events_rejected_total`, `agentops_trace_spans_total`, `agentops_trace_export_failures_total`, `agentops_observability_errors_total`, `agentops_backend_info`.
  - Implemented strict label cardinality bounding and privacy screening via `BoundedLabel`: dynamic labels (`agent_id`, `provider`, `model`, `tool_name`, rejection `code`) are sanitised, truncated to 64 chars, and capped at 50–200 distinct values, with overflow collapsing into `"other"`. Run IDs, user IDs, raw prompts, and exception messages are strictly forbidden in metric labels.
  - Added `GET /metrics` endpoint with authentication boundary: requires `AGENTOPS_METRICS_TOKEN` bearer token; open in development environment when token is unset; disabled with 503 outside development when token is unset.
  - Built OpenTelemetry trace pipeline (`backend/agentops_backend/tracing.py`) materializing spans from accepted telemetry events:
    - Root span `agent.run` correlated 1:1 with run `trace_id` and `root_span_id`.
    - Child spans `llm.chat` and `tool.<name>` with parent span correlation.
    - Request span `ingest.batch` with batch size and outcome attributes.
  - Implemented error-preserving sampling: error runs/calls are always exported, while healthy runs sample according to `AGENTOPS_TRACE_SAMPLE_RATIO` (default 1.0).
  - Implemented `ResilientExporter` with bounded `BatchSpanProcessor` queue: exporter crashes/timeouts are caught, counted, and never leak into ingestion or disrupt normal agent workflows.
  - Created observability coordinator facade (`backend/agentops_backend/observability.py`) executed strictly post-commit with exception swallowing.
  - Configured Prometheus scrape target (`infra/prometheus/prometheus.yml`) with bearer token credentials file.
  - Configured Grafana Tempo (`infra/tempo/tempo.yml`) with OTLP receivers on 4317 (gRPC) and 4318 (HTTP), and 30-day block retention.
  - Provisioned Grafana datasources (`infra/grafana/provisioning/datasources/datasources.yml`) and dashboards (`infra/grafana/provisioning/dashboards/dashboards.yml`).
  - Created initial operational overview dashboard (`infra/grafana/dashboards/agentops-overview.json`) with panels for run rate, error ratio, p50/p95 duration, token consumption, tool/LLM rates, ingestion latency, and pipeline health.
  - Updated `infra/docker-compose.yml` to define the full local stack (PostgreSQL, Backend, Prometheus, Tempo, Grafana) with pinned container versions and zero committed secrets.
  - Authored comprehensive observability guide (`docs/observability.md`) covering data flow, architecture, ports, metrics catalog, label safety, sampling, failure behaviour, local startup, manual verification, and troubleshooting.
  - Added full test coverage for metrics, tracing, and static infra configurations.
- **Files added/modified:**
  - Added: `backend/agentops_backend/metrics.py`, `tracing.py`, `observability.py`
  - Added: `backend/tests/test_metrics.py`, `test_tracing.py`, `test_infra_config.py`
  - Added: `infra/prometheus/prometheus.yml`, `infra/tempo/tempo.yml`
  - Added: `infra/grafana/provisioning/datasources/datasources.yml`, `infra/grafana/provisioning/dashboards/dashboards.yml`
  - Added: `infra/grafana/dashboards/agentops-overview.json`
  - Added: `docs/observability.md`
  - Modified: `.env.example`, `backend/pyproject.toml`, `backend/agentops_backend/config.py`, `backend/agentops_backend/ingestion.py`, `backend/agentops_backend/routes.py`, `backend/agentops_backend/main.py`, `infra/docker-compose.yml`, `PROGRESS.md`, `IMPLEMENTATION_STATUS.md`
- **Commands run and actual results:**
  - `pip install "prometheus-client>=0.20,<1.0" "opentelemetry-api>=1.27,<2.0" "opentelemetry-sdk>=1.27,<2.0" "opentelemetry-exporter-otlp-proto-http>=1.27,<2.0" pytest pytest-cov httpx requests pyyaml` — PASS (installed in .venv)
  - `pip install -e "sdk[dev]"` — PASS (responses installed, SDK package editable)
  - `pytest tests/test_metrics.py` — PASS (18 tests passed)
  - `pytest tests/test_tracing.py` — PASS (14 tests passed, including real OTLP/HTTP wire export)
  - `pytest tests/test_infra_config.py` — PASS (13 tests passed, validated compose, scrape configs, and dashboard metric queries)
  - `pytest --cov=agentops_backend --cov-report=term-missing` (backend) — PASS (134 passed, 95% test coverage)
  - `pytest sdk/tests` (sdk) — PASS (3 passed, 86% test coverage)
  - `docker --version` — BLOCKED (Docker CLI is not installed on the Windows host environment)
- **Tests added/updated:**
  - `tests/test_metrics.py`: 18 tests (metric names/types, label bounding/privacy, lifecycle counting, failure accounting, duplicate idempotency, rejection categorization, /metrics auth, fault isolation)
  - `tests/test_tracing.py`: 14 tests (root/child span correlation to run history, failure status propagation, request span emission, out-of-order event handling, attribute sanitization, error-preserving sampling, exporter fault tolerance, real OTLP/HTTP wire export)
  - `tests/test_infra_config.py`: 13 tests (compose service definitions, pinned images, secret hygiene, published ports, Prometheus scrape configuration, Tempo receiver ports and retention, Grafana datasources, dashboard queries against real metrics, bounded query grouping)
- **Acceptance criteria evidence:**
  - Metrics reflect actual test runs: ✅ (`tests/test_metrics.py::test_counters_reflect_a_successful_run`, `test_failed_run_counts_as_error`, `test_llm_and_tool_failures_and_reported_durations`)
  - Prometheus scrapes the intended targets: ✅ (`tests/test_metrics.py::test_metrics_open_in_development_without_token`, `tests/test_infra_config.py::test_prometheus_scrapes_backend_with_token_file`)
  - Detailed traces can be retrieved from chosen backend: ✅ (`tests/test_tracing.py::test_spans_are_exported_over_real_otlp_http` verifies real OTLP/HTTP protobuf export)
  - Trace and run identifiers can be correlated: ✅ (`tests/test_tracing.py::test_run_exports_root_and_child_spans_correlated_to_run`)
  - Local developer can start observability stack from documented commands: ✅ (`docs/observability.md`, `infra/docker-compose.yml`, `tests/test_infra_config.py`)
- **Decisions/assumptions:**
  - SDK remains free from direct OpenTelemetry dependencies; the backend materializes correlated spans from accepted telemetry events using the SDK-provided trace and span IDs.
  - Backend uses an isolated `CollectorRegistry` instance to prevent global registry pollution across tests and process instances.
  - Traces are exported asynchronously via a bounded queue; trace exporter failures never crash or block the ingestion pipeline.
  - Spans of error runs/calls are always exported regardless of sample ratio.
  - Default retention: Tempo traces 30 days (`block_retention: 720h`), Prometheus 30 days (`retention.time=30d`), PostgreSQL runs 90 days.
- **Blockers/known limitations:**
  - Docker CLI is not installed on the Windows host environment; live container deployment was validated via static compose/config testing and in-process real OTLP HTTP receiver tests. Full container execution is cataloged in the manual verification checklist.
- **Human verification steps:**
  - Follow the manual verification checklist in `docs/observability.md` (or the end-of-phase report below).
- **Status at end:** `READY_FOR_REVIEW`
- **Human approval:** None yet.
- **Next permitted action:** Await human owner review and explicit approval of Phase 4 before beginning Phase 5.

### 2026-10-14 — Progress Tracking & Documentation Synchronization
- **Status at start:** `READY_FOR_REVIEW`
- **Work performed:**
  - Audited repository progress across all project documentation.
  - Reconciled and synchronized `PROGRESS.md` header snapshot and phase checklist, `README.md`, and `docs/implementation-plan.md` to consistently record:
    - Phase 1: `APPROVED`
    - Phase 2: `APPROVED`
    - Phase 3: `APPROVED`
    - Phase 4: `READY_FOR_REVIEW` (implementation, tests, and configuration complete, awaiting explicit owner review and approval)
    - Phases 5–10: `NOT_STARTED`
- **Files added/modified:**
  - Modified: `PROGRESS.md`, `README.md`, `docs/implementation-plan.md`
- **Commands run and actual results:**
  - `git status -s` — PASS (clean working tree before edits)
  - `git log -n 5 --oneline` — PASS (verified commits through Phase 4)
- **Tests added/updated:** None (documentation synchronization only).
- **Acceptance criteria evidence:**
  - All progress tracking documents (`IMPLEMENTATION_STATUS.md`, `PROGRESS.md`, `README.md`, `docs/implementation-plan.md`) are now mutually consistent.
- **Decisions/assumptions:**
  - Maintained mandatory rule from `AGENTS.md`: Phase 4 remains `READY_FOR_REVIEW` and cannot be marked `APPROVED` without explicit human authorization.
- **Blockers/known limitations:** None.
- **Human verification steps:**
  - Review updated progress summaries across `PROGRESS.md`, `IMPLEMENTATION_STATUS.md`, `README.md`, and `docs/implementation-plan.md`.
- **Status at end:** `READY_FOR_REVIEW`
- **Human approval:** None yet for Phase 4.
- **Next permitted action:** Await human owner review and explicit approval of Phase 4 before beginning Phase 5.

## Append-only session entry template

Copy this section for each meaningful work session and fill it with observed facts.

### YYYY-MM-DD — Phase N: Phase Name
- **Status at start:**
- **Work performed:**
- **Files added/modified:**
- **Commands run and actual results:**
  - `command` — PASS / FAIL / BLOCKED / NOT RUN; evidence or reason.
- **Tests added/updated:**
- **Acceptance criteria evidence:**
- **Decisions/assumptions:**
- **Blockers/known limitations:**
- **Human verification steps:**
- **Status at end:** `IN_PROGRESS` / `BLOCKED` / `READY_FOR_REVIEW`
- **Human approval:** None unless explicitly provided by the owner.
- **Next permitted action:** Wait for review / continue current phase after requested fixes / begin next phase only after explicit approval.


