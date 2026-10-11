# Observability Stack — Metrics, Tracing, Dashboards (Phase 4)

How AgentOps turns ingested telemetry into Prometheus metrics and OpenTelemetry traces.

## Data flow

```
 agent + SDK ──HTTP──▶ backend  POST /v1/telemetry/events
                         │  1. validate + persist (PostgreSQL)      ◀── source of truth
                         │  2. COMMIT
                         │  3. best-effort, post-commit:
                         ├──▶ Prometheus metrics (in-process registry)
                         │         ▲ scrape GET /metrics (bearer token)
                         │         └── Prometheus :9090 ──▶ Grafana :3000
                         └──▶ OTel spans ─ bounded queue ─ OTLP/HTTP ─▶ Tempo :4318
                                                                          └──▶ Grafana (Tempo datasource)
```

Metrics and spans are produced **after the database commit** and are strictly best-effort:
an exception while recording them is swallowed and counted in
`agentops_observability_errors_total`; it never changes the ingestion response or the stored data.

## Ports

| Service | Port | Purpose |
|---|---|---|
| backend | 8000 | API, `/metrics` |
| Prometheus | 9090 | Metrics store / UI |
| Tempo | 3200 | Trace query API |
| Tempo | 4317 / 4318 | OTLP gRPC / HTTP receivers |
| Grafana | 3000 | Dashboards (provisioned: Prometheus + Tempo datasources) |
| PostgreSQL | 5432 | Run history |

## Configuration (environment)

| Variable | Default | Meaning |
|---|---|---|
| `AGENTOPS_METRICS_TOKEN` | unset | Bearer token required to scrape `/metrics` |
| `AGENTOPS_OTLP_ENDPOINT` | unset (tracing off) | OTLP/HTTP traces URL, e.g. `http://tempo:4318/v1/traces` |
| `AGENTOPS_TRACE_SAMPLE_RATIO` | `1.0` | Fraction of **non-error** traces exported (0.0–1.0) |
| `AGENTOPS_TRACE_QUEUE_SIZE` | `2048` | Bounded span queue; overflow is dropped by the OTel SDK (logged), never blocks |
| `AGENTOPS_TRACE_EXPORT_TIMEOUT_SECONDS` | `5` | Per-export timeout |
| `AGENTOPS_SERVICE_NAME` | `agentops-backend` | OTel `service.name` |

### `/metrics` access boundary

| Environment | `AGENTOPS_METRICS_TOKEN` | Result |
|---|---|---|
| any | set | Requires `Authorization: Bearer <token>` (constant-time compare), else `401` |
| `development` | unset | Open (local convenience only) |
| not `development` | unset | `503 metrics_disabled` (safe default) |

API keys (`ingest`/`read`) and the admin token do **not** grant access to `/metrics`.
In production also keep `/metrics` off the public network (internal network or reverse-proxy allow-list).

## Metrics

| Metric | Type | Labels |
|---|---|---|
| `agentops_runs_total` | Counter | `agent_id`, `environment`, `status` |
| `agentops_run_duration_seconds` | Histogram | `agent_id`, `environment` |
| `agentops_llm_calls_total` | Counter | `agent_id`, `provider`, `model`, `status` |
| `agentops_llm_call_duration_seconds` | Histogram | `agent_id`, `provider`, `model` |
| `agentops_tool_calls_total` | Counter | `agent_id`, `tool_name`, `status` |
| `agentops_tool_call_duration_seconds` | Histogram | `agent_id`, `tool_name` |
| `agentops_tokens_total` | Counter | `agent_id`, `provider`, `model`, `token_type` |
| `agentops_ingestion_requests_total` | Counter | `status` (HTTP code), `endpoint` (fixed route) |
| `agentops_ingestion_latency_seconds` | Histogram | `endpoint` |
| `agentops_events_total` | Counter | `outcome` = accepted / duplicate / rejected |
| `agentops_events_rejected_total` | Counter | `code` (rejection code) |
| `agentops_trace_spans_total` | Counter | `outcome` = queued / sampled_out / invalid_ids |
| `agentops_trace_export_failures_total` | Counter | — |
| `agentops_observability_errors_total` | Counter | — |
| `agentops_backend_info` | Gauge | `version` |

Counting semantics: duplicates and idempotent retries never increment run/LLM/tool/token counters;
a run is counted **once**, when it first becomes terminal (also for out-of-order streams);
the duration histogram is observed once, when the duration first becomes computable.
LLM/tool duration histograms only receive observations when the SDK reports `duration_ms`.

### Label safety

* `run_id`, `event_id`, `trace_id`, `project_id`, user IDs, prompts and error messages are **never** labels.
* `agent_id`, `provider`, `model`, `tool_name`, `code` pass through `BoundedLabel`: values are sanitised
  to `[A-Za-z0-9_.\-/:]`, truncated to 64 chars and capped at 50–200 distinct values per label
  (overflow becomes `other`). Missing values become `unknown`.
* Enforced by tests (`tests/test_metrics.py`, `tests/test_infra_config.py`).

## Traces

SDK-instrumented agents send events, so the backend **materialises spans from accepted events**
using identifiers already stored on the run — this is what makes traces correlate with run history:

| Span | `trace_id` | `span_id` | Parent |
|---|---|---|---|
| `agent.run` | run `trace_id` | run `root_span_id` | — |
| `llm.chat` / `tool.<name>` | run `trace_id` | event `span_id` or derived hash of the event id | root span |
| `ingest.batch` | new trace (live request span) | generated | — |

Span attributes: `agentops.{project_id,agent_id,run_id,environment,run_status}`, `llm.{provider,model,*_tokens}`,
`tool.{name,type}`, `error.type`. Prompts, outputs, secrets and free-form metadata are never attached
(enforced by an allow-list test). Span start/end come from event timestamps (and reported `duration_ms`).

**Decision:** the SDK stays free of an OpenTelemetry dependency; "SDK operations" are represented by the
backend-built spans above. The SDK already generates the `trace_id`/`root_span_id` used for correlation.

### Sampling & retention defaults

* Spans of **error** runs/calls are always exported. Other spans are exported with probability
  `AGENTOPS_TRACE_SAMPLE_RATIO`, decided deterministically from the trace id (default `1.0` = everything).
* **Limitation:** with a ratio < 1.0, the *non-error children* of a sampled-out run that later fails are not
  exported (the error root span and any failing call spans are). `ingest.batch` request spans follow the ratio.
* Retention (assumption A-005): Tempo traces 30 days (`block_retention: 720h`), Prometheus 30 days
  (`--storage.tsdb.retention.time=30d`), runs 90 days (PostgreSQL, Phase 9).

### Failure behaviour

* Export is asynchronous via a bounded `BatchSpanProcessor`; a full queue drops spans instead of blocking.
* Exporter exceptions/failures are logged (type only, no payload) and counted in
  `agentops_trace_export_failures_total`.
* If Tempo is down: ingestion still returns `202`, data is still persisted, `/health/ready` stays green,
  `agentops_trace_export_failures_total` increases.

## Local startup

```powershell
# repo root; create .env from .env.example and set the required values
# (POSTGRES_PASSWORD, AGENTOPS_SECRET_KEY, AGENTOPS_ADMIN_TOKEN, AGENTOPS_METRICS_TOKEN, GRAFANA_ADMIN_PASSWORD)
docker compose -f infra/docker-compose.yml --env-file .env up -d --build
docker compose -f infra/docker-compose.yml ps
```

Running the backend directly (e.g. against Neon) without containers:

```powershell
# in .env:  AGENTOPS_METRICS_TOKEN=...   AGENTOPS_OTLP_ENDPOINT=http://localhost:4318/v1/traces
cd backend ; uvicorn agentops_backend.main:app --port 8000
curl http://localhost:8000/metrics -H "Authorization: Bearer $env:AGENTOPS_METRICS_TOKEN"
```
(If you run Prometheus/Tempo in containers while the backend runs on the host, change the scrape target in
`infra/prometheus/prometheus.yml` to `host.docker.internal:8000` and the OTLP endpoint to
`http://localhost:4318/v1/traces`.)

## Manual verification checklist

> **Not yet executed in the development environment** — Docker was unavailable (see `PROGRESS.md`).
> Run these on a machine with Docker before approving Phase 4.

1. `docker compose -f infra/docker-compose.yml --env-file .env up -d --build` → all services `running`/`healthy`.
2. Prometheus `http://localhost:9090/targets` → `agentops-backend` and `prometheus` are **UP**.
3. Generate data: `python -m agentops_backend.seed` (synthetic) or `python examples/simple_agent.py`.
4. In Prometheus run `sum by (status) (agentops_runs_total)` and
   `histogram_quantile(0.95, sum by (le) (rate(agentops_run_duration_seconds_bucket[5m])))`.
5. Grafana `http://localhost:3000` (admin / `GRAFANA_ADMIN_PASSWORD`) → folder **AgentOps** → *Operational Overview* shows data.
6. Grafana → Explore → Tempo → search `{ resource.service.name = "agentops-backend" }` → open an `agent.run` trace
   and confirm child `llm.chat` / `tool.*` spans; check `agentops.run_id` equals the run in `GET /v1/projects/{id}/runs`.
7. `curl localhost:8000/metrics` (no token) → `401`; with token → `200`. Scan the output: no prompts, secrets, run IDs or trace IDs.
8. `docker compose -f infra/docker-compose.yml stop tempo`, send telemetry → ingestion still `202`, runs queryable,
   `agentops_trace_export_failures_total` rises; start Tempo again.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Prometheus target `agentops-backend` DOWN, `401` | `AGENTOPS_METRICS_TOKEN` differs between backend and Prometheus container, or unset |
| Target DOWN, `503 metrics_disabled` | backend `AGENTOPS_ENV` is not `development` and no token is set |
| No traces in Tempo | `AGENTOPS_OTLP_ENDPOINT` unset (tracing off); wrong host; check `agentops_trace_export_failures_total` and backend logs |
| Only error traces appear | `AGENTOPS_TRACE_SAMPLE_RATIO` < 1.0 (by design) |
| LLM/tool duration panels empty | SDK/agent does not report `duration_ms` in call events |
| Tempo container exits with permission errors on `/var/tempo` | volume ownership; recreate the `tempodata` volume (`docker compose down -v` deletes local trace data) |
