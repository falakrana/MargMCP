# Trace Details and Run History — Developer Guide

> Phase 5 documentation. Covers the timeline API, span assembly, retention semantics,
> privacy settings, and the manual verification checklist.

---

## Overview

Phase 5 makes every agent run **explainable from start to finish**. The backend
assembles a span timeline entirely from its own `runs` and `events` tables — it
does not depend on the external OTLP trace backend (Tempo) being reachable at
read time.

```
┌──────────┐    POST /v1/telemetry/events    ┌─────────────────────────┐
│ SDK Agent│ ──────────────────────────────► │  Backend (ingestion)    │
└──────────┘                                 │  • runs table           │
                                             │  • events table         │
GET /v1/projects/{pid}/runs/{rid}/timeline   │  • async OTLP export ──►│ Tempo
◄────────────────────────────────────────────│    (write-only at read) │
                                             └─────────────────────────┘
```

---

## New API Endpoints

### `GET /v1/projects/{project_id}/runs/{run_id}/timeline`

Returns the full, paginated timeline for one run.

**Auth:** `read` scope API key.

**Query parameters:**

| Parameter       | Default | Max  | Description                             |
|-----------------|---------|------|-----------------------------------------|
| `max_spans`     | 1000    | 1000 | Maximum spans in the span tree          |
| `event_page`    | 1       | —    | Raw event page number                   |
| `event_page_size` | 100   | 500  | Raw events per page                     |

**Response schema:** `RunTimelineOut`

```json
{
  "run": { /* RunOut — full run metadata */ },
  "is_complete": true,
  "trace_data_may_have_expired": false,
  "spans": [
    {
      "span_id": "abcdef1234567890",
      "parent_span_id": null,
      "name": "agent.run",
      "event_id": "",
      "event_type": "run_started",
      "start_time": "2026-10-01T10:00:00Z",
      "end_time": "2026-10-01T10:00:05Z",
      "duration_ms": 5000,
      "status": "ok",
      "attributes": { "agentops.run_id": "...", "agentops.run_status": "success" },
      "parent_missing": false
    },
    {
      "span_id": "11223344aabbccdd",
      "parent_span_id": "abcdef1234567890",
      "name": "llm.chat",
      "event_id": "evt-abc123",
      "event_type": "llm_call_completed",
      "start_time": "2026-10-01T10:00:01Z",
      "end_time": "2026-10-01T10:00:02Z",
      "duration_ms": 1000,
      "status": "ok",
      "attributes": { "llm.provider": "openai", "llm.model": "gpt-4o" },
      "parent_missing": false
    }
  ],
  "spans_truncated": false,
  "span_count": 2,
  "events": [ /* raw event list (paged) */ ],
  "total_event_count": 4,
  "event_page": 1,
  "event_page_size": 100,
  "trace_link": null,
  "correlation_links": {
    "run_id": "...",
    "trace_id": "...",
    "root_span_id": "...",
    "run_metadata_expires_at": "2027-01-01T00:00:00+00:00",
    "trace_data_expires_at": "2026-11-01T00:00:00+00:00",
    "metric_window": { "from": "...", "to": "..." }
  }
}
```

### `GET /v1/projects/{project_id}/runs/by-trace/{trace_id}`

Redirects (`307`) to the timeline endpoint for the run matching the given
OpenTelemetry `trace_id`. Useful for jumping from a Tempo / Jaeger trace into
the AgentOps run record.

**Auth:** `read` scope API key.

**Errors:**
- `404` — no run found for that trace ID, or trace ID format is invalid.
- `403` — API key does not belong to `project_id`.

---

## Span Assembly

Spans are assembled **from local storage** using the following rules:

1. **Root span** (`agent.run`) — synthesised from the `Run` record. Its
   `span_id` is always the run's `root_span_id`. Duration = `run.duration_ms`.
   Status = `"running"` if incomplete, `"ok"` / `"error"` / `"cancelled"` once terminal.

2. **Child spans** — assembled from `llm_call_completed`, `llm_call_failed`,
   `tool_call_completed`, `tool_call_failed` events. Each child span:
   - Uses `data.span_id` if valid (16 hex chars), otherwise a deterministic
     SHA-256 hash of `project_id + event_id`.
   - Uses `data.parent_span_id` if it matches a known span, otherwise falls
     back to the root span.
   - Sets `parent_missing = True` when `parent_span_id` references a span that
     is not in the current result set (missing or in a different page).

3. **Ordering** — spans are returned root-first, then child spans sorted by
   `start_time` ascending.

4. **Attributes** — only identifiers, names, and bounded scalars. Prompts,
   responses, and secrets are **never** span attributes.

---

## Completeness Flags

| Condition                                        | `is_complete` |
|--------------------------------------------------|---------------|
| Run has a terminal event and `ended_at` is set   | `true`        |
| No terminal event yet                            | `false`       |
| Run started but no events ingested yet           | `false`       |

---

## Retention and the `trace_data_may_have_expired` Flag

This service stores runs and events for `AGENTOPS_RUN_RETENTION_DAYS` (default 90).
The OTLP backend (Tempo) keeps traces for `AGENTOPS_TRACE_RETENTION_DAYS` (default 30).

When `run.started_at + trace_retention_days < now`, the timeline API sets
`trace_data_may_have_expired = true`. The local timeline is still fully served
from the `events` table, but querying Tempo for this trace ID may return nothing.

```
Day 0   ────────────────────────────────────────────────────► time
         Run happens
                          Day 30: Tempo trace window expires
                          (trace_data_may_have_expired = true)
                                          Day 90: Run record deleted
                                          (404 from this API)
```

### Behaviour when metadata and trace data are out of sync

| Scenario                                      | Behaviour                                               |
|-----------------------------------------------|---------------------------------------------------------|
| Run record exists, Tempo trace still valid    | Full timeline + `trace_link` points to Tempo           |
| Run record exists, Tempo trace expired        | Full timeline served locally; `trace_data_may_have_expired = true` |
| Run record expired (past 90 days)             | 404 from this API; no timeline served                  |
| Tempo trace exists but run was never ingested | Tempo UI shows spans; this API has no record (404)     |

---

## Privacy Settings

### Default (payload capture off)

`AGENTOPS_PAYLOAD_CAPTURE_ENABLED=false` (default)

- Raw event `data` returned **without** `summary`, `output_summary`,
  `input_summary`, and `result_summary` fields.
- Span attributes never contain prompts, responses, or secrets.
- Error metadata (`error_type`, `error_summary`) is included because it is
  already in the run record (stored at ingest time without raw content).

### Payload capture enabled

`AGENTOPS_PAYLOAD_CAPTURE_ENABLED=true`

- `summary`-type fields are **included** in raw event `data` when present.
- This flag must be explicitly set; it is never on by default.
- Even with this flag, prompts and API keys rejected at ingest time are never
  stored and cannot appear in any response.

---

## Correlation Links

Every timeline response includes `correlation_links` with:

| Field                    | Description                                                  |
|--------------------------|--------------------------------------------------------------|
| `run_id`                 | Unique run identifier (matches URL parameter)               |
| `trace_id`               | OpenTelemetry trace ID (32 hex chars)                       |
| `root_span_id`           | Root span ID (16 hex chars)                                 |
| `run_metadata_expires_at`| ISO-8601 timestamp after which the run record may be gone   |
| `trace_data_expires_at`  | ISO-8601 timestamp after which Tempo traces may be gone     |
| `metric_window`          | `{"from": ..., "to": ...}` UTC window for Prometheus queries|

### Generating OTLP UI deep-links

Set `AGENTOPS_OTLP_UI_BASE_URL=http://localhost:3000` (Grafana URL). The
timeline API will populate `trace_link` with a Tempo deep-link:

```
http://localhost:3000/explore?traceId={trace_id}
```

---

## Configuration Reference

| Variable                          | Default          | Description                             |
|-----------------------------------|------------------|-----------------------------------------|
| `AGENTOPS_PAYLOAD_CAPTURE_ENABLED`| `false`          | Include payload summaries in timelines  |
| `AGENTOPS_RUN_RETENTION_DAYS`     | `90`             | Days to keep run records                |
| `AGENTOPS_TRACE_RETENTION_DAYS`   | `30`             | Days OTLP backend retains traces        |
| `AGENTOPS_OTLP_UI_BASE_URL`       | *(unset)*        | Grafana base URL for trace deep-links   |

---

## Manual Verification Checklist

### 1. Inspect a successful run

```bash
# Create project and key (replace with your admin token)
curl -X POST http://localhost:8000/v1/admin/projects \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -d '{"name": "test"}'
# Note: project_id and api_key from response

# List runs for the project
curl http://localhost:8000/v1/projects/<PROJECT_ID>/runs \
  -H "Authorization: Bearer <READ_KEY>"

# Inspect a specific run's timeline
curl http://localhost:8000/v1/projects/<PROJECT_ID>/runs/<RUN_ID>/timeline \
  -H "Authorization: Bearer <READ_KEY>"
```

Expected:
- `is_complete = true`, `run.status = "success"`
- Root span `agent.run` with no parent
- Child spans ordered by `start_time` ascending

### 2. Inspect a failed run

Same as above but look for:
- `run.status = "error"`, `run.error_type` populated
- Root span `status = "error"`
- `is_complete = true`

### 3. Inspect a run with nested LLM/tool operations

Send events with explicit `span_id` and `parent_span_id` in event data. In
the timeline:
- Verify `parent_span_id` on each child matches the expected parent
- Verify `parent_missing = false` for all spans

### 4. Inspect a run with incomplete trace data

Send only `run_started` and some child events, no terminal event. In the timeline:
- `is_complete = false`
- Root span `status = "running"`

### 5. Verify time range filters and pagination

```bash
# Page 1, 5 events per page
curl "http://localhost:8000/v1/projects/<PID>/runs/<RID>/timeline?event_page=1&event_page_size=5" \
  -H "Authorization: Bearer <READ_KEY>"

# Page 2
curl "http://localhost:8000/v1/projects/<PID>/runs/<RID>/timeline?event_page=2&event_page_size=5" \
  -H "Authorization: Bearer <READ_KEY>"
```

Expected: `total_event_count` is constant; each page returns up to `event_page_size` events.

### 6. Confirm sensitive inputs/outputs are not exposed by default

1. Send an event whose `data` contains a `summary` field.
2. Fetch the timeline without changing settings.
3. Verify `summary` is **absent** from all events in the response.
4. Set `AGENTOPS_PAYLOAD_CAPTURE_ENABLED=true`, restart, and repeat —
   now `summary` should appear.

### 7. Look up a run by trace ID

```bash
# Look up from trace_id to run
curl "http://localhost:8000/v1/projects/<PID>/runs/by-trace/<TRACE_ID>" \
  -H "Authorization: Bearer <READ_KEY>" \
  -L  # follow the 307 redirect
```

Expected: 307 redirect to `/timeline`, then full timeline JSON.
