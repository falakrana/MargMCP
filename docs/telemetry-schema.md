# AgentOps MCP — Telemetry Schema (v1)

This document defines the canonical telemetry model shared by the SDK, adapters, ingestion API, and storage layers.

All integrations MUST produce data conforming to this schema. Framework adapters translate framework-specific events into these canonical types.

---

## 1. Schema Versioning

| Field | Value |
|---|---|
| `schema_version` | `"1.0"` |

All telemetry payloads include `schema_version`. The ingestion API rejects payloads with unsupported versions with a clear error. Older schema versions are never silently reinterpreted.

---

## 2. Common Fields

Every telemetry record includes these base fields:

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | string | ✅ | `"1.0"` |
| `event_id` | string (UUID) | ✅ | Globally unique, idempotency key |
| `agent_id` | string (UUID) | ✅ | Agent that produced this event |
| `project_id` | string (UUID) | ✅ | Project the agent belongs to |
| `run_id` | string (UUID) | ✅ | Run this event belongs to |
| `environment` | string | ✅ | `"development"`, `"staging"`, `"production"` |
| `timestamp` | string (ISO-8601 UTC) | ✅ | When the event occurred |
| `event_type` | string (enum) | ✅ | See §3 |
| `deployment_version` | string | ❌ | Application/deployment version |

---

## 3. Event Types

### 3.1 Run Lifecycle

| Event Type | Description |
|---|---|
| `run_started` | Agent run has begun |
| `run_completed` | Agent run finished successfully |
| `run_failed` | Agent run finished with an error |
| `run_cancelled` | Agent run was cancelled |

### 3.2 LLM Operations

| Event Type | Description |
|---|---|
| `llm_call_started` | LLM request initiated |
| `llm_call_completed` | LLM request returned successfully |
| `llm_call_failed` | LLM request failed |

### 3.3 Tool Operations

| Event Type | Description |
|---|---|
| `tool_call_started` | Tool invocation initiated |
| `tool_call_completed` | Tool invocation succeeded |
| `tool_call_failed` | Tool invocation failed |

### 3.4 Generic

| Event Type | Description |
|---|---|
| `custom_event` | Application-defined event with custom attributes |

---

## 4. Run Record

Persisted in PostgreSQL. This is the searchable execution record.

| Field | Type | Required | Description |
|---|---|---|---|
| `run_id` | UUID | ✅ | Primary key |
| `agent_id` | UUID | ✅ | FK → agents |
| `project_id` | UUID | ✅ | FK → projects |
| `trace_id` | string | ✅ | OTel-compatible trace ID (32-char hex) |
| `root_span_id` | string | ✅ | Root span for this run (16-char hex) |
| `environment` | string | ✅ | |
| `status` | enum | ✅ | `running`, `success`, `error`, `cancelled`, `unknown` |
| `started_at` | timestamp (UTC) | ✅ | |
| `ended_at` | timestamp (UTC) | ❌ | Null while running |
| `duration_ms` | integer | ❌ | Computed from started_at / ended_at |
| `error_type` | string | ❌ | Error classification |
| `error_summary` | string | ❌ | Redacted summary, max 1024 chars |
| `deployment_version` | string | ❌ | |
| `sdk_version` | string | ✅ | SDK version that produced the telemetry |
| `llm_call_count` | integer | ❌ | Aggregated count |
| `tool_call_count` | integer | ❌ | Aggregated count |
| `total_prompt_tokens` | integer | ❌ | Sum when available |
| `total_completion_tokens` | integer | ❌ | Sum when available |
| `total_tokens` | integer | ❌ | Sum when available |
| `metadata` | JSON | ❌ | Safe key-value pairs, max 10 keys, 256 chars/value |
| `created_at` | timestamp (UTC) | ✅ | Ingestion time |
| `updated_at` | timestamp (UTC) | ✅ | Last update time |

---

## 5. Trace Span

Exported via OTLP to Tempo. Also referenced in query responses.

| Field | Type | Required | Description |
|---|---|---|---|
| `trace_id` | string (32-char hex) | ✅ | Groups all spans in a trace |
| `span_id` | string (16-char hex) | ✅ | Unique span identifier |
| `parent_span_id` | string (16-char hex) | ❌ | Null for root span |
| `run_id` | UUID | ✅ | Attribute linking span to run |
| `operation_name` | string | ✅ | e.g. `"agent.run"`, `"llm.chat"`, `"tool.search"` |
| `operation_type` | enum | ✅ | `agent`, `llm`, `tool`, `retrieval`, `http`, `custom` |
| `start_time` | timestamp (UTC) | ✅ | |
| `end_time` | timestamp (UTC) | ✅ | |
| `duration_ms` | integer | ✅ | |
| `status` | enum | ✅ | `ok`, `error`, `unset` |
| `error_type` | string | ❌ | |
| `error_message` | string | ❌ | Redacted |
| `attributes` | map<string, string> | ❌ | Safe metadata (see §5.1) |

### 5.1 Standard Span Attributes

| Attribute Key | Applies To | Description |
|---|---|---|
| `agentops.agent_id` | all | Agent identifier |
| `agentops.project_id` | all | Project identifier |
| `agentops.run_id` | all | Run identifier |
| `agentops.environment` | all | Environment name |
| `llm.provider` | llm | e.g. `"openai"`, `"anthropic"` |
| `llm.model` | llm | e.g. `"gpt-4o"`, `"claude-3.5-sonnet"` |
| `llm.prompt_tokens` | llm | Token count (integer as string) |
| `llm.completion_tokens` | llm | Token count |
| `llm.total_tokens` | llm | Token count |
| `tool.name` | tool | Tool/function name |
| `tool.type` | tool | e.g. `"function"`, `"api"` |
| `http.method` | http | HTTP method |
| `http.status_code` | http | Response status code |
| `http.url` | http | Redacted URL (no query params with secrets) |

**Forbidden attributes** (never set by default): `llm.prompt`, `llm.response`, `tool.input`, `tool.output`, or any field containing raw user content, secrets, or PII.

---

## 6. Ingestion API Payload

### 6.1 Event Batch (`POST /v1/telemetry/events`)

```json
{
  "schema_version": "1.0",
  "project_id": "uuid",
  "batch": [
    {
      "event_id": "uuid",
      "agent_id": "uuid",
      "run_id": "uuid",
      "event_type": "run_started",
      "timestamp": "2026-10-04T05:30:00Z",
      "environment": "production",
      "data": {
        "trace_id": "abc123...",
        "root_span_id": "def456...",
        "deployment_version": "1.2.3",
        "metadata": {"team": "ml-platform"}
      }
    }
  ]
}
```

### 6.2 Constraints

| Constraint | Limit |
|---|---|
| Max batch size | 100 events |
| Max payload size | 1 MB |
| Max metadata keys | 10 |
| Max metadata value length | 256 chars |
| Max error_summary length | 1024 chars |
| Timestamp tolerance | ±24 hours from server time |

---

## 7. Metrics Definitions

Exposed at `GET /metrics` (Prometheus scrape).

| Metric | Type | Labels | Description |
|---|---|---|---|
| `agentops_runs_total` | Counter | `agent_id`, `environment`, `status` | Total runs by status |
| `agentops_run_duration_seconds` | Histogram | `agent_id`, `environment` | Run duration distribution |
| `agentops_llm_calls_total` | Counter | `agent_id`, `provider`, `model`, `status` | LLM call count |
| `agentops_llm_call_duration_seconds` | Histogram | `agent_id`, `provider`, `model` | LLM call latency |
| `agentops_tool_calls_total` | Counter | `agent_id`, `tool_name`, `status` | Tool call count |
| `agentops_tool_call_duration_seconds` | Histogram | `agent_id`, `tool_name` | Tool call latency |
| `agentops_tokens_total` | Counter | `agent_id`, `provider`, `model`, `token_type` | Token usage (prompt/completion) |
| `agentops_ingestion_requests_total` | Counter | `status`, `endpoint` | Ingestion API request count |
| `agentops_ingestion_latency_seconds` | Histogram | `endpoint` | Ingestion API latency |

**Label cardinality rules:**
- `agent_id`: bounded by registered agents (low hundreds max)
- `provider`, `model`: bounded by known providers
- `tool_name`: bounded by registered tool names
- **Never** use: `run_id`, `user_id`, `trace_id`, prompt text, error messages

---

## 8. MCP Tool Input/Output Contracts (Summary)

Detailed schemas will be finalized in Phase 7. Initial contract boundaries:

| Tool | Key Inputs | Key Outputs |
|---|---|---|
| `list_agents` | `project_id` | Array of agent summaries |
| `get_agent_metrics` | `agent_id`, `time_range` | Metric summaries (counts, rates, percentiles) |
| `list_runs` | `agent_id`, `status?`, `time_range`, `page`, `page_size` | Paginated run summaries |
| `get_run_details` | `run_id` | Full run record + event summary |
| `get_trace` | `trace_id` or `run_id` | Bounded span tree |
| `get_error_summary` | `agent_id`, `time_range` | Grouped error types + counts |
| `compare_runs` | `run_id_a`, `run_id_b` | Side-by-side comparison |

**All tools:** require auth, enforce tenant scoping, apply max result limits, return structured JSON with `data` + `metadata` envelope.
