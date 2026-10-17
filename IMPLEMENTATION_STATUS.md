# AgentOps MCP — Implementation Status

> Current-state snapshot. Kept synchronized with `PROGRESS.md`.

## Current State

| Field                         | Value                                                      |
| ----------------------------- | ---------------------------------------------------------- |
| **Current Phase**             | Phase 6 — Monitoring Dashboard                             |
| **Phase Status**              | `NOT_STARTED`                                              |
| **Last Approved Phase**       | Phase 5                                                    |
| **Next Phase**                | Phase 6 — Monitoring Dashboard (`NOT_STARTED`)             |

---

## Phase Status Table

| Phase | Name                                                        | Status               |
| ----- | ----------------------------------------------------------- | -------------------- |
| 1     | Repository Discovery, Architecture, and Implementation Plan | `APPROVED`           |
| 2     | Core SDK and First Instrumentation Adapter                  | `APPROVED`           |
| 3     | Ingestion API, Persistence, and Query Services              | `APPROVED`           |
| 4     | Metrics, Prometheus, and Trace Export Pipeline              | `APPROVED`           |
| 5     | Trace Details and Run History                               | `APPROVED`           |
| 6     | Monitoring Dashboard                                        | `NOT_STARTED`        |
| 7     | MCP Server and Read-Only Monitoring Tools                   | `NOT_STARTED`        |
| 8     | AI Diagnostic Assistant                                     | `NOT_STARTED`        |
| 9     | Security, Reliability, and Performance Hardening            | `NOT_STARTED`        |
| 10    | Deployment, End-to-End Pilot, and Release Readiness         | `NOT_STARTED`        |

---

## Phase 5 — Completed Tasks

- [x] API contract for run timeline joining run metadata, events, and trace references without external DB dependency (`backend/agentops_backend/trace_service.py`)
- [x] Trace retrieval by run ID with assembled parent-child span ordering (root span synthesised from Run record; child spans from events)
- [x] Run-history filtering by time range, agent, status, metadata — all previously implemented in Phase 3 `queries.py`, confirmed working
- [x] Event timeline ordering: events returned in `(timestamp ASC, event_id ASC)` stable order; late-arriving events handled correctly
- [x] Duration and status for each span: root span duration from `run.duration_ms`; child span duration from `data.duration_ms`; status `ok/error/cancelled/running` correctly derived
- [x] Incomplete trace detection: `is_complete` is False when no terminal event or `ended_at` is NULL; root span status `"running"` for incomplete runs
- [x] Missing parent span detection: `parent_missing=True` flag on spans referencing a `parent_span_id` not in the result set
- [x] Error summaries and safe error metadata: `error_type`, `error_summary` surfaced in span attributes; raw prompts/secrets never included
- [x] Optional payload summaries: `summary`/`output_summary` fields stripped by default (`AGENTOPS_PAYLOAD_CAPTURE_ENABLED=false`); included only when explicitly enabled
- [x] Pagination for spans (`max_spans` cap) and events (`event_page` / `event_page_size`) — independent pagination controls
- [x] Correlation links: `run_id`, `trace_id`, `root_span_id`, retention expiry timestamps, metric time window per run
- [x] Trace deep-link generation to OTLP UI (Grafana/Tempo) via `AGENTOPS_OTLP_UI_BASE_URL`
- [x] `trace_data_may_have_expired` flag when run is older than `AGENTOPS_TRACE_RETENTION_DAYS`
- [x] Lookup run by OTLP trace ID (`GET /runs/by-trace/{trace_id}`) with 307 redirect to timeline
- [x] Retention semantics documented: run record vs OTLP trace data lifecycle, out-of-sync scenarios (`docs/trace-and-history.md`)
- [x] New config settings: `payload_capture_enabled`, `run_retention_days`, `trace_retention_days`, `otlp_ui_base_url`
- [x] 38 Phase 5 tests, 172 total backend tests passing, 95% code coverage

---

## Phase 5 — Acceptance Criteria

| Criterion                                                        | Status  | Evidence                                                                                               |
| ---------------------------------------------------------------- | ------- | ------------------------------------------------------------------------------------------------------ |
| Developer can find a run and inspect its timeline                | ✅ PASS | `TestCompleteTrace::test_successful_run_timeline`, `test_failed_run_timeline`                          |
| Nested spans presented in correct relationship                   | ✅ PASS | `TestNestedOperations::test_nested_spans_have_correct_parent`                                          |
| Missing trace data communicated accurately                       | ✅ PASS | `TestMissingParentSpans::test_child_with_unknown_parent_flagged`, `trace_data_may_have_expired` flag   |
| Large result sets are bounded and paginated                      | ✅ PASS | `TestPagination::test_event_pagination_*`, `test_max_spans_limit_respected`                            |
| Privacy settings honored consistently                            | ✅ PASS | `TestPayloadCapture::test_payload_fields_stripped_by_default`                                          |

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
