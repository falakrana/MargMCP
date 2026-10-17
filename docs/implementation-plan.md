# AgentOps MCP — Implementation Plan (Phase Checklist)

This is the operational checklist derived from `implementation.md`. Each phase has testable exit criteria.

---

## Phase 1 — Repository Discovery, Architecture, and Implementation Plan

**Status:** `APPROVED`

- [X] Inspect repository files, directory structure, and existing code
- [X] Inspect PRD/SRS and architecture documents
- [X] Check Git status and uncommitted changes
- [X] Summarize what exists vs. what is needed
- [X] Identify gaps against the implementation plan
- [X] Propose modular directory structure
- [X] Document architecture and component boundaries (`docs/architecture.md`)
- [X] Document data flow, trust boundaries, storage responsibilities
- [X] Define telemetry schema v1 (`docs/telemetry-schema.md`)
- [X] Define API/MCP contract boundaries
- [X] Record assumptions and decisions (`docs/assumptions-and-decisions.md`)
- [X] Create `IMPLEMENTATION_STATUS.md`
- [X] Create testing strategy (`docs/testing-strategy.md`)
- [X] Create `.gitignore` and `.env.example`
- [X] Human review and approval

---

## Phase 2 — Core SDK and First Instrumentation Adapter

**Status:** `APPROVED`

- [X] SDK package structure and public API
- [X] Configuration (endpoint, API key, project/agent IDs, env, timeouts, sampling, privacy)
- [X] Run lifecycle (start, events, output summary, end, error, cancel)
- [X] Context management (auto-finalize on exception)
- [X] Exporter abstraction + HTTP exporter
- [X] Bounded buffering/batching with configurable flush
- [X] Idempotent event IDs
- [X] Redaction hooks; payload capture OFF by default
- [X] Trace/run context propagation
- [X] Generic Python wrapper/decorator
- [X] Example agent + integration test
- [X] Package docs + `.env.example` update
- [X] Tests: lifecycle, exception, cancellation, exporter timeout, retry, redaction, disabled SDK, nested context
- [X] Human review and approval

---

## Phase 3 — Ingestion API, Persistence, and Query Services

**Status:** `APPROVED`

- [X] FastAPI app structure (routers, services, schemas, repository layer, config, DI)
- [X] API-key authentication (hashed storage)
- [X] Project/agent registration flow
- [X] Ingestion endpoints (run lifecycle, events, spans)
- [X] Schema validation (version, IDs, timestamps, payload size, status transitions)
- [X] PostgreSQL persistence + idempotent writes
- [X] Query services (list/filter runs, run details, agent metadata, error summaries)
- [X] Pagination + time-range filters
- [X] Tenant/project authorization at service layer
- [X] Health/readiness endpoints
- [X] Database indexes + migrations (Alembic)
- [X] Seed/demo data (clearly marked synthetic)
- [X] API documentation + error codes
- [X] Human review and approval

---

## Phase 4 — Metrics, Prometheus, and Trace Export Pipeline

**Status:** `APPROVED`

- [X] Backend service metrics instrumentation
- [X] Application metrics (runs, durations, LLM/tool ops, ingestion health)
- [X] Bounded label review
- [X] Prometheus metrics endpoint
- [X] Prometheus scrape config
- [X] OTel tracing for backend requests
- [X] Span naming + attribute consistency
- [X] Tempo trace export config
- [X] Trace retention + sampling defaults
- [X] Grafana provisioning (datasources + initial dashboards)
- [X] Telemetry pipeline failure isolation
- [X] Documentation (ports, data flow, troubleshooting)

---

## Phase 5 — Trace Details and Run History

**Status:** `APPROVED`

- [X] API contract joining run metadata + events + trace references
- [X] Trace retrieval by trace/run ID with span ordering
- [X] Run history filtering (time, agent, status, metadata)
- [X] Event timeline ordering + late/out-of-order handling
- [X] Error summaries + safe stack metadata
- [X] Optional redacted I/O summaries
- [X] Pagination for large traces/histories
- [X] Correlation links (run ↔ trace ↔ metric windows ↔ errors)
- [X] Retention behavior documentation

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
