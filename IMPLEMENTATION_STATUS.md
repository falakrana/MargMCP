# AgentOps MCP — Implementation Status

> Current-state snapshot. Kept synchronized with `PROGRESS.md`.

## Current State

| Field                         | Value                                                |
| ----------------------------- | ---------------------------------------------------- |
| **Current Phase**       | Phase 8 — AI Diagnostic Assistant |
| **Phase Status**        | `READY_FOR_REVIEW`                                   |
| **Last Approved Phase** | Phase 7                                              |
| **Next Phase**          | Phase 9 — Security, Reliability, and Performance Hardening (not started; requires explicit approval of Phase 8) |

---

## Phase Status Table

| Phase | Name                                                        | Status               |
| ----- | ----------------------------------------------------------- | -------------------- |
| 1     | Repository Discovery, Architecture, and Implementation Plan | `APPROVED`         |
| 2     | Core SDK and First Instrumentation Adapter                  | `APPROVED`         |
| 3     | Ingestion API, Persistence, and Query Services              | `APPROVED`         |
| 4     | Metrics, Prometheus, and Trace Export Pipeline              | `APPROVED`         |
| 5     | Trace Details and Run History                               | `APPROVED`         |
| 6     | Monitoring Dashboard                                        | `APPROVED`         |
| 7     | MCP Server and Read-Only Monitoring Tools                   | `APPROVED`         |
| 8     | AI Diagnostic Assistant                                     | `READY_FOR_REVIEW` |
| 9     | Security, Reliability, and Performance Hardening            | `NOT_STARTED`      |
| 10    | Deployment, End-to-End Pilot, and Release Readiness         | `NOT_STARTED`      |

---

## Phase 5 — Completed Tasks

- [X] API contract for run timeline joining run metadata, events, and trace references without external DB dependency (`backend/agentops_backend/trace_service.py`)
- [X] Trace retrieval by run ID with assembled parent-child span ordering (root span synthesised from Run record; child spans from events)
- [X] Run-history filtering by time range, agent, status, metadata — all previously implemented in Phase 3 `queries.py`, confirmed working
- [X] Event timeline ordering: events returned in `(timestamp ASC, event_id ASC)` stable order; late-arriving events handled correctly
- [X] Duration and status for each span: root span duration from `run.duration_ms`; child span duration from `data.duration_ms`; status `ok/error/cancelled/running` correctly derived
- [X] Incomplete trace detection: `is_complete` is False when no terminal event or `ended_at` is NULL; root span status `"running"` for incomplete runs
- [X] Missing parent span detection: `parent_missing=True` flag on spans referencing a `parent_span_id` not in the result set
- [X] Error summaries and safe error metadata: `error_type`, `error_summary` surfaced in span attributes; raw prompts/secrets never included
- [X] Optional payload summaries: `summary`/`output_summary` fields stripped by default (`AGENTOPS_PAYLOAD_CAPTURE_ENABLED=false`); included only when explicitly enabled
- [X] Pagination for spans (`max_spans` cap) and events (`event_page` / `event_page_size`) — independent pagination controls
- [X] Correlation links: `run_id`, `trace_id`, `root_span_id`, retention expiry timestamps, metric time window per run
- [X] Trace deep-link generation to OTLP UI (Grafana/Tempo) via `AGENTOPS_OTLP_UI_BASE_URL`
- [X] `trace_data_may_have_expired` flag when run is older than `AGENTOPS_TRACE_RETENTION_DAYS`
- [X] Lookup run by OTLP trace ID (`GET /runs/by-trace/{trace_id}`) with 307 redirect to timeline
- [X] Retention semantics documented: run record vs OTLP trace data lifecycle, out-of-sync scenarios (`docs/trace-and-history.md`)
- [X] New config settings: `payload_capture_enabled`, `run_retention_days`, `trace_retention_days`, `otlp_ui_base_url`
- [X] 38 Phase 5 tests, 172 total backend tests passing, 95% code coverage

---

## Phase 5 — Acceptance Criteria

| Criterion                                         | Status  | Evidence                                                                                                 |
| ------------------------------------------------- | ------- | -------------------------------------------------------------------------------------------------------- |
| Developer can find a run and inspect its timeline | ✅ PASS | `TestCompleteTrace::test_successful_run_timeline`, `test_failed_run_timeline`                        |
| Nested spans presented in correct relationship    | ✅ PASS | `TestNestedOperations::test_nested_spans_have_correct_parent`                                          |
| Missing trace data communicated accurately        | ✅ PASS | `TestMissingParentSpans::test_child_with_unknown_parent_flagged`, `trace_data_may_have_expired` flag |
| Large result sets are bounded and paginated       | ✅ PASS | `TestPagination::test_event_pagination_*`, `test_max_spans_limit_respected`                          |
| Privacy settings honored consistently             | ✅ PASS | `TestPayloadCapture::test_payload_fields_stripped_by_default`                                          |

---

## Known Issues & Notes

- Docker CLI is not installed in the Windows host environment (inherited from Phase 4).
- `trace_data_may_have_expired` is computed from config-driven retention days; it does not query Tempo live.
- `payload_capture_enabled=true` mode is tested via unit tests with the settings override; no integration test with Tempo.

---

## Files Added in Phase 5

```
backend/agentops_backend/trace_service.py
backend/tests/test_trace_history.py
docs/trace-and-history.md
```

## Files Modified in Phase 5

```
.env.example
backend/agentops_backend/config.py
backend/agentops_backend/routes.py
backend/agentops_backend/schemas.py
PROGRESS.md
IMPLEMENTATION_STATUS.md
```

---

## Phase 6 — Completed Tasks

- [X] Initialized modern Vite + React 19 + TypeScript frontend application in `frontend/`
- [X] Implemented minimalist whitish design system in `frontend/src/index.css` (custom tokens: `#ffffff` canvas, `#f8fafc` subtle background, `#e2e8f0` crisp borders, `#0f172a` high-contrast typography, `#4f46e5` accent)
- [X] Created reusable UI component library in `frontend/src/components/ui.tsx` (`StatusBadge`, `StatCard`, `Spinner`, `EmptyState`, `Alert`, `Pagination`, `Tabs`, `SkeletonRows`)
- [X] Implemented secure API client in `frontend/src/api.ts` with error handling (`ApiError`), session Bearer auth (`sessionStorage`), and endpoints for projects, agents, runs, traces, and error summaries
- [X] Implemented `AuthContext` (`frontend/src/context/AuthContext.tsx`) for project ID and API key session management with non-blocking key prompt
- [X] Built application shell and navigation in `frontend/src/components/Sidebar.tsx` and `frontend/src/App.tsx`
- [X] Implemented Overview Dashboard (`frontend/src/pages/OverviewPage.tsx`) with KPI stat cards, Recharts volume area chart, latency chart, status distribution, active agents, and recent runs
- [X] Implemented Agents Directory (`frontend/src/pages/AgentsPage.tsx`) with runtime stats and search filter
- [X] Implemented Agent Detail Page (`frontend/src/pages/AgentDetailPage.tsx`) with agent-level metadata and filtered runs view
- [X] Implemented Run History Page (`frontend/src/pages/RunHistoryPage.tsx`) with status, agent ID, and environment filters, and pagination
- [X] Implemented Run Detail Page (`frontend/src/pages/RunDetailPage.tsx`) with waterfall span tree, duration bars, expandable JSON event stream, and correlation deep links tab
- [X] Implemented Trace Explorer (`frontend/src/pages/TracesPage.tsx`) for OTLP traces
- [X] Implemented Errors & Diagnostics Page (`frontend/src/pages/ErrorsPage.tsx`) with error type aggregation and drill-down to filtered run history
- [X] Implemented Settings Page (`frontend/src/pages/SettingsPage.tsx`) with project credentials, live backend health checks, privacy posture, and SDK code snippet
- [X] Configured development CORS middleware in `backend/agentops_backend/main.py` allowing local Vite dev server
- [X] Implemented Vitest unit test suite in `frontend/src/utils.test.ts` and `frontend/src/api.test.ts` (20 passed)
- [X] Documented Phase 6 architecture, features, and manual verification checklist in `docs/dashboard.md`

---

## Phase 6 — Acceptance Criteria

| Criterion                                                                     | Status  | Evidence                                                          |
| ----------------------------------------------------------------------------- | ------- | ----------------------------------------------------------------- |
| Minimalist whitish UI aesthetic with clean layout and responsive design       | ✅ PASS | `frontend/src/index.css`                                        |
| Fast production build & zero TypeScript errors                                | ✅ PASS | `npm run build` completed in 636ms with 0 errors                |
| Comprehensive unit testing of utils & API client                              | ✅ PASS | `npm run test` (20 passed)                                      |
| Backend tests continue passing with CORS configuration                        | ✅ PASS | `pytest backend/tests` (172 passed)                             |
| Secure auth handling (session-only, no credentials exposed in client bundles) | ✅ PASS | `frontend/src/context/AuthContext.tsx`, `frontend/src/api.ts` |
| Run timeline, span hierarchy, and event inspection                            | ✅ PASS | `frontend/src/pages/RunDetailPage.tsx`                          |

---

## Files Added in Phase 6

```
frontend/package.json
frontend/vite.config.ts
frontend/tsconfig.json
frontend/index.html
frontend/public/favicon.svg
frontend/src/index.css
frontend/src/main.tsx
frontend/src/App.tsx
frontend/src/api.ts
frontend/src/utils.ts
frontend/src/context/AuthContext.tsx
frontend/src/components/ui.tsx
frontend/src/components/Sidebar.tsx
frontend/src/pages/OverviewPage.tsx
frontend/src/pages/AgentsPage.tsx
frontend/src/pages/AgentDetailPage.tsx
frontend/src/pages/RunHistoryPage.tsx
frontend/src/pages/RunDetailPage.tsx
frontend/src/pages/TracesPage.tsx
frontend/src/pages/ErrorsPage.tsx
frontend/src/pages/SettingsPage.tsx
frontend/src/utils.test.ts
frontend/src/api.test.ts
docs/dashboard.md
```

## Files Modified in Phase 6

```
backend/agentops_backend/main.py
docs/implementation-plan.md
PROGRESS.md
IMPLEMENTATION_STATUS.md
```

---

## Phase 7 — Completed Tasks

- [X] Official Python MCP SDK (`mcp` 1.30, `FastMCP`) added as bounded dependency `mcp>=1.2,<2.0`; entry point `agentops-mcp` / `python -m agentops_backend.mcp_server`
- [X] Protocol-independent tool layer `backend/agentops_backend/mcp_tools.py` delegating to shared `queries` / `trace_service` (new shared `queries.agent_metrics`)
- [X] Seven read-only tools: `list_agents`, `get_agent_metrics`, `list_runs`, `get_run_details`, `get_trace`, `get_error_summary`, `compare_runs` (all annotated `readOnlyHint`)
- [X] Strict validation: ID pattern, enums, ISO-8601 times, reversed ranges, max window (30d), page/limit caps, `max_spans` cap
- [X] AuthN/AuthZ on every call: DB-verified API key with `read` scope; project fixed by key; mismatching `project_id` rejected; stdio key from env, HTTP key from `Authorization` header
- [X] Structured outputs with `kind`, `source` (project, data source, generated_at) and explicit `unavailable` indicators
- [X] Safe errors (`<code>: <message>`), no stack traces/SQL/secrets; storage failure -> `storage_unavailable`
- [X] Output safety: no raw event payloads, run metadata hidden unless payload capture enabled, text truncated to 256 chars
- [X] 42 new tests incl. real MCP stdio client smoke test (`backend/tests/test_mcp.py`)
- [X] Docs `docs/mcp-server.md` (transport, auth, tools, errors, client config, manual checklist); `.env.example` placeholders

## Phase 7 — Acceptance Criteria

| Criterion                                              | Status  | Evidence                                                                 |
| ------------------------------------------------------ | ------- | ------------------------------------------------------------------------ |
| MCP client can connect and list tools                  | ✅ PASS | `TestMcpProtocolSmoke::test_stdio_client_lists_and_calls_tools`         |
| Each tool returns real AgentOps data via shared services | ✅ PASS | `TestToolOutputs`                                                        |
| Invalid requests return controlled errors              | ✅ PASS | `TestValidationAndBounds`, `TestFailureModes`                           |
| Authorization and result limits apply consistently     | ✅ PASS | `TestAuth`, `TestValidationAndBounds`                                   |
| All tools remain read-only                             | ✅ PASS | `TestReadOnlySurface`                                                    |

## Phase 7 — Known Issues & Notes

- `backend/tests/test_infra_config.py::test_compose_defines_observability_services` FAILS: `infra/docker-compose.yml` has the `postgres` service commented out (owner commit `2d7e924`, Neon in use). Pre-existing; unrelated to Phase 7; not modified.
- Client config JSON follows the common `mcpServers` convention and is not verified against any specific client; documented as such.
- Streamable-HTTP transport implemented and documented but only the stdio transport is exercised by the automated smoke test.
- `get_agent_metrics` is computed from the run store (not live Prometheus queries); duration percentiles use the most recent 10,000 runs (`durations_sampled` flag).
- No MCP-specific rate limiting (Phase 9).

## Files Added in Phase 7

```
backend/agentops_backend/mcp_server.py
backend/agentops_backend/mcp_tools.py
backend/tests/test_mcp.py
docs/mcp-server.md
```

## Files Modified in Phase 7

```
backend/agentops_backend/config.py
backend/agentops_backend/queries.py
backend/pyproject.toml
.env.example
PROGRESS.md
IMPLEMENTATION_STATUS.md
```

---

## Phase 8 — Completed Tasks

- [X] Assistant package `backend/agentops_backend/assistant/` (`evidence`, `engine`, `providers`, `prompts`, `models`)
- [X] Role, tool permissions, context limits and response format defined (system prompt + `DiagnosticReport` schema: scope, findings, likely_explanations, evidence, unknown, next_checks)
- [X] Evidence retrieved only through the authorised read-only Phase 7 tool layer (7 read tools); deterministic, budgeted workflow: scope → metrics/recent runs → anomalous/failed runs → traces → baseline comparison → single LLM call
- [X] Citation verification: unresolvable refs removed, uncited statements dropped; `evidence[]` built from retrieved records, never model text
- [X] Facts (`findings`) vs hypotheses (`likely_explanations` with confidence + uncertainty); gaps reported in `unknown`
- [X] Provider config via `DIAGNOSTIC_*` env (disabled by default); OpenAI-compatible provider (Groq/OpenAI presets, custom base URL)
- [X] Bounds: tool-call budget, context chars, spans, max tokens, timeout, bounded retries (429/504/502 mapped to safe errors)
- [X] Prompt-injection defence: escaped/delimited data block, untrusted-data system prompt, suspicious-content counter
- [X] Read-only enforcement: no write/exec code (static test), no DB change, remediation claims stripped
- [X] Safe invocation logging (scope kind, outcome, counts, duration only)
- [X] REST `POST /v1/projects/{id}/diagnose/{run|agent}` and MCP tools `diagnose_run` / `diagnose_agent`
- [X] 68 deterministic tests with scripted LLM + mocked HTTP; docs `docs/diagnostic-assistant.md`

## Phase 8 — Acceptance Criteria

| Criterion                                              | Status  | Evidence                                                                    |
| ------------------------------------------------------ | ------- | --------------------------------------------------------------------------- |
| Answers using real retrieved telemetry                 | ✅ PASS (scripted LLM; live model NOT RUN) | `TestKnownFailures`, `TestCitations`             |
| Separates evidence from hypotheses, exposes uncertainty | ✅ PASS | `TestKnownFailures::test_observations_and_hypotheses_are_separate_fields`, `TestMissingEvidence` |
| Does not invent run IDs, metrics, costs, root causes   | ✅ PASS | `TestCitations`, `TestMissingEvidence::test_conflicting_model_output_*`     |
| Respects tenant access and privacy/redaction settings  | ✅ PASS | `TestTenancy`, `TestInjectionAndPrivacy`                                    |
| Cannot mutate monitored systems                        | ✅ PASS | `TestReadOnly`                                                              |

## Phase 8 — Known Issues & Notes

- Pre-existing, unrelated: `backend/tests/test_infra_config.py::test_compose_defines_observability_services` still FAILS (compose `postgres` service commented out in owner commit `2d7e924`). Not modified.
- Last full run: `pytest backend/tests --cov=agentops_backend` → 282 passed, 1 failed (above), coverage 94%. Linting/type checks NOT RUN (none configured).
- No live LLM provider call was made; real-model quality is unverified until the owner runs the manual checklist with a real key.
- Only OpenAI-compatible providers are implemented; with hosted providers, redacted telemetry summaries leave the infrastructure.
- No rate limiting / cost budget on diagnose endpoints (Phase 9). No dashboard UI for diagnostics (not requested).
- Evidence comes from the run store (not live Prometheus/Tempo). Baseline = lower-quartile-duration success (documented heuristic).
- Phase 7 `test_mcp.py` assertions were updated for the two new tools.

## Files Added in Phase 8

```
backend/agentops_backend/assistant/__init__.py
backend/agentops_backend/assistant/engine.py
backend/agentops_backend/assistant/evidence.py
backend/agentops_backend/assistant/models.py
backend/agentops_backend/assistant/prompts.py
backend/agentops_backend/assistant/providers.py
backend/tests/test_assistant.py
docs/diagnostic-assistant.md
```

## Files Modified in Phase 8

```
backend/agentops_backend/config.py
backend/agentops_backend/main.py
backend/agentops_backend/mcp_server.py
backend/agentops_backend/routes.py
backend/pyproject.toml
backend/tests/test_mcp.py
.env.example
docs/implementation-plan.md
PROGRESS.md
IMPLEMENTATION_STATUS.md
```
