# AgentOps MCP — Implementation Plan (Phase Checklist)

This is the operational checklist derived from `implementation.md`. Each phase has testable exit criteria.

---

## Phase 1 — Repository Discovery, Architecture, and Implementation Plan
**Status:** `IN_PROGRESS`

- [x] Inspect repository files, directory structure, and existing code
- [x] Inspect PRD/SRS and architecture documents
- [x] Check Git status and uncommitted changes
- [x] Summarize what exists vs. what is needed
- [x] Identify gaps against the implementation plan
- [x] Propose modular directory structure
- [x] Document architecture and component boundaries (`docs/architecture.md`)
- [x] Document data flow, trust boundaries, storage responsibilities
- [x] Define telemetry schema v1 (`docs/telemetry-schema.md`)
- [x] Define API/MCP contract boundaries
- [x] Record assumptions and decisions (`docs/assumptions-and-decisions.md`)
- [x] Create `IMPLEMENTATION_STATUS.md`
- [x] Create testing strategy (`docs/testing-strategy.md`)
- [x] Create `.gitignore` and `.env.example`
- [ ] Human review and approval

---

## Phase 2 — Core SDK and First Instrumentation Adapter
**Status:** `NOT_STARTED`

- [ ] SDK package structure and public API
- [ ] Configuration (endpoint, API key, project/agent IDs, env, timeouts, sampling, privacy)
- [ ] Run lifecycle (start, events, output summary, end, error, cancel)
- [ ] Context management (auto-finalize on exception)
- [ ] Exporter abstraction + HTTP exporter
- [ ] Bounded buffering/batching with configurable flush
- [ ] Idempotent event IDs
- [ ] Redaction hooks; payload capture OFF by default
- [ ] Trace/run context propagation
- [ ] Generic Python wrapper/decorator
- [ ] Example agent + integration test
- [ ] Package docs + `.env.example` update
- [ ] Tests: lifecycle, exception, cancellation, exporter timeout, retry, redaction, disabled SDK, nested context

---

## Phase 3 — Ingestion API, Persistence, and Query Services
**Status:** `NOT_STARTED`

- [ ] FastAPI app structure (routers, services, schemas, repository layer, config, DI)
- [ ] API-key authentication (hashed storage)
- [ ] Project/agent registration flow
- [ ] Ingestion endpoints (run lifecycle, events, spans)
- [ ] Schema validation (version, IDs, timestamps, payload size, status transitions)
- [ ] PostgreSQL persistence + idempotent writes
- [ ] Query services (list/filter runs, run details, agent metadata, error summaries)
- [ ] Pagination + time-range filters
- [ ] Tenant/project authorization at service layer
- [ ] Health/readiness endpoints
- [ ] Database indexes + migrations (Alembic)
- [ ] Seed/demo data (clearly marked synthetic)
- [ ] API documentation + error codes

---

## Phase 4 — Metrics, Prometheus, and Trace Export Pipeline
**Status:** `NOT_STARTED`

- [ ] Backend service metrics instrumentation
- [ ] Application metrics (runs, durations, LLM/tool ops, ingestion health)
- [ ] Bounded label review
- [ ] Prometheus metrics endpoint
- [ ] Prometheus scrape config
- [ ] OTel tracing for backend requests
- [ ] Span naming + attribute consistency
- [ ] Tempo trace export config
- [ ] Trace retention + sampling defaults
- [ ] Grafana provisioning (datasources + initial dashboards)
- [ ] Telemetry pipeline failure isolation
- [ ] Documentation (ports, data flow, troubleshooting)

---

## Phase 5 — Trace Details and Run History
**Status:** `NOT_STARTED`

- [ ] API contract joining run metadata + events + trace references
- [ ] Trace retrieval by trace/run ID with span ordering
- [ ] Run history filtering (time, agent, status, metadata)
- [ ] Event timeline ordering + late/out-of-order handling
- [ ] Error summaries + safe stack metadata
- [ ] Optional redacted I/O summaries
- [ ] Pagination for large traces/histories
- [ ] Correlation links (run ↔ trace ↔ metric windows ↔ errors)
- [ ] Retention behavior documentation

---

## Phase 6 — Monitoring Dashboard
**Status:** `NOT_STARTED`

- [ ] React + TypeScript setup
- [ ] Authentication/session handling
- [ ] App shell + navigation
- [ ] Overview dashboard page
- [ ] Projects/agents list + detail pages
- [ ] Run history with filters + pagination
- [ ] Run detail + event timeline
- [ ] Trace/span explorer
- [ ] Error/failure summary
- [ ] Settings page
- [ ] Charts (run volume, success/failure, latency, tokens)
- [ ] Loading/empty/error states
- [ ] Accessibility + responsive layout
- [ ] Frontend tests

---

## Phase 7 — MCP Server and Read-Only Monitoring Tools
**Status:** `NOT_STARTED`

- [ ] MCP SDK integration
- [ ] Thin server calling shared query services
- [ ] Tools: list_agents, get_agent_metrics, list_runs, get_run_details, get_trace, get_error_summary, compare_runs
- [ ] Strict input schemas + defaults + pagination
- [ ] Structured output format
- [ ] Auth + tenant scoping per tool call
- [ ] Time-window + query bounds validation
- [ ] Read-only enforcement
- [ ] Safe error messages
- [ ] Client smoke test + config examples

---

## Phase 8 — AI Diagnostic Assistant
**Status:** `NOT_STARTED`

- [ ] Role definition, tool permissions, context limits, response format
- [ ] MCP tool integration for evidence retrieval
- [ ] Bounded investigation workflow
- [ ] Evidence references for all claims
- [ ] Observation vs. hypothesis distinction
- [ ] Missing evidence reporting
- [ ] Provider/model config via env vars
- [ ] Timeouts + bounded tool calls + token limits
- [ ] Prompt-injection defense
- [ ] Read-only enforcement
- [ ] Diagnostic invocation logging
- [ ] Deterministic tests with mocked LLM

---

## Phase 9 — Security, Reliability, and Performance Hardening
**Status:** `NOT_STARTED`

- [ ] Threat model review
- [ ] Auth/authz/isolation/key-rotation verification
- [ ] Sensitive data leakage audit
- [ ] Rate limits + request/query bounds
- [ ] Failure mode testing (DNS, network, backend, DB down)
- [ ] Retry policy review
- [ ] Buffer/queue limit verification
- [ ] Database index + query plan review
- [ ] Synthetic load testing
- [ ] Prometheus cardinality check
- [ ] Retention/deletion workflow testing
- [ ] Dependency + secret scanning
- [ ] Operational health checks + structured logs
- [ ] Security + performance findings report

---

## Phase 10 — Deployment, End-to-End Pilot, and Release Readiness
**Status:** `NOT_STARTED`

- [ ] Deployment target review
- [ ] Production container definitions
- [ ] Dev vs. prod config separation
- [ ] HTTPS / reverse proxy config
- [ ] Secret injection + backup/restore procedures
- [ ] CI checks (lint, type, test, build)
- [ ] Operational runbook
- [ ] Non-production deployment
- [ ] Pilot agent instrumentation
- [ ] Full path validation (agent → SDK → ingestion → DB → metrics → traces → dashboard → MCP → assistant)
- [ ] Failure case testing
- [ ] Release readiness report
