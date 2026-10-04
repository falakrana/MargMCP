# AgentOps MCP — Architecture

## 1. System Overview

AgentOps MCP is an observability and diagnostic platform for AI agents. It collects telemetry from instrumented agents, stores it as metrics / traces / run history, exposes it through a dashboard and MCP interface, and provides an AI diagnostic assistant for evidence-based failure investigation.

## 2. High-Level Architecture

```text
┌──────────────────────────────────────────────────────────┐
│                   Monitored AI Agents                    │
│  (Python applications using LLMs, tools, retrieval, …)  │
└───────────────┬──────────────────────┬───────────────────┘
                │                      │
        AgentOps SDK           Framework Adapters
        (direct code)          (decorators/callbacks)
                │                      │
                └──────────┬───────────┘
                           │  Telemetry (HTTP/OTLP)
                           ▼
              ┌────────────────────────┐
              │   Ingestion API        │
              │   (FastAPI)            │
              │   • Auth + validation  │
              │   • Normalize events   │
              │   • Route to stores    │
              └──┬─────┬──────┬───────┘
                 │     │      │
     ┌───────────┘     │      └───────────┐
     ▼                 ▼                  ▼
┌──────────┐   ┌─────────────┐   ┌──────────────┐
│Prometheus│   │ PostgreSQL  │   │ Tempo (OTLP) │
│ (metrics)│   │ (runs,      │   │ (traces /    │
│          │   │  events,    │   │  spans)      │
│          │   │  agents)    │   │              │
└────┬─────┘   └──────┬──────┘   └──────┬───────┘
     │                │                 │
     └────────┬───────┴─────────┬───────┘
              │  Query / Service Layer  │
              └──────┬──────────┬───────┘
                     │          │
              ┌──────┘          └──────┐
              ▼                        ▼
     ┌──────────────┐         ┌────────────────┐
     │   Dashboard  │         │ AgentOps MCP   │
     │ (React + TS) │         │ Server         │
     │ + Grafana    │         │ (read-only     │
     │              │         │  tools)        │
     └──────────────┘         └───────┬────────┘
                                      │
                              ┌───────┴────────┐
                              │ AI Diagnostic  │
                              │ Assistant      │
                              │ (evidence-     │
                              │  based,        │
                              │  read-only)    │
                              └────────────────┘
```

## 3. Component Responsibilities

### 3.1 AgentOps SDK (`sdk/`)

| Concern | Detail |
|---|---|
| Initialization | `AgentOps.from_env()` or explicit config |
| Run lifecycle | `start_run → record events → set_output_summary → end_run` |
| Context propagation | Thread-local / contextvars for trace/run IDs |
| Exporter abstraction | Pluggable — default HTTP exporter to Ingestion API |
| Buffering | Bounded in-memory batch queue with configurable flush interval |
| Failure mode | Best-effort; telemetry errors never crash the agent |
| Redaction | Configurable hooks; payload capture OFF by default |

### 3.2 Framework Adapters (`sdk/adapters/`)

Translate framework-specific lifecycle events (e.g., LangChain callbacks) into the canonical AgentOps telemetry schema. Share the same exporter and batching infrastructure as the SDK.

### 3.3 Ingestion API (`backend/`)

- FastAPI application with versioned routes (`/v1/...`)
- API-key authentication per project/agent
- Schema validation (Pydantic models matching `telemetry-schema.md`)
- Idempotent writes keyed on `event_id`
- Routes telemetry → PostgreSQL (runs/events), Prometheus (metrics), OTLP (traces)
- Health/readiness endpoints (`/health/live`, `/health/ready`)

### 3.4 PostgreSQL — Run & Event Store

- Stores: organizations, projects, agents, API keys, runs, events
- Indexed by: `agent_id`, `run_id`, `status`, `started_at`, `environment`
- Run records reference `trace_id` but do NOT duplicate span data

### 3.5 Prometheus — Metrics Store

- Scraped from the backend `/metrics` endpoint
- Counters: `agentops_runs_total{status, agent, env}`
- Histograms: `agentops_run_duration_seconds{agent, env}`
- Histograms: `agentops_llm_call_duration_seconds{provider, model}`
- Counters: `agentops_ingestion_requests_total{status}`
- **No** high-cardinality labels (no run_id, user_id, prompts)

### 3.6 Tempo — Trace Store

- Receives spans via OTLP (gRPC or HTTP)
- Stores parent/child span trees per `trace_id`
- Queried by `trace_id`; tag-based search optional
- Retention configurable independently from PostgreSQL

### 3.7 Dashboard (`dashboard/`)

- React + TypeScript SPA
- Authenticates against the backend API
- Pages: Overview, Agents, Run History, Run Detail / Trace Explorer, Errors, Settings
- Embeds Grafana panels for operational metrics or links to standalone Grafana

### 3.8 AgentOps MCP Server (`mcp_server/`)

- Thin Python MCP server using the maintained MCP SDK
- Read-only tools calling the shared Query/Service layer
- Enforces auth + tenant scoping on every tool call
- Bounded responses, pagination, timeout enforcement

### 3.9 AI Diagnostic Assistant (`assistant/`)

- LLM-powered investigation agent (provider-agnostic via config)
- Invokes authorized MCP tools to retrieve evidence
- Returns structured diagnostic reports with evidence references
- Read-only; cannot modify production systems
- Prompt-injection-safe: telemetry content treated as data, not instructions

## 4. Trust Boundaries

```text
┌─ UNTRUSTED ─────────────────────────────────────────────┐
│  Agent telemetry payloads (may contain prompt injection, │
│  malformed data, oversized payloads)                     │
└──────────────────────────┬──────────────────────────────┘
                           ▼
              ┌── TRUST BOUNDARY 1: Ingestion ──┐
              │  API-key auth                    │
              │  Schema validation               │
              │  Payload size limits              │
              │  Rate limiting                   │
              │  Redaction                       │
              └──────────────┬───────────────────┘
                             ▼
┌─ INTERNAL / TRUSTED ────────────────────────────────────┐
│  PostgreSQL, Prometheus, Tempo                          │
│  Query/Service Layer                                    │
└──────────────────────────┬──────────────────────────────┘
                           ▼
              ┌── TRUST BOUNDARY 2: Consumer access ──┐
              │  Dashboard auth (session/token)        │
              │  MCP server auth + tenant scoping      │
              │  Bounded queries, pagination           │
              │  No raw DB access exposed              │
              └──────────────┬─────────────────────────┘
                             ▼
┌─ PARTIALLY TRUSTED ─────────────────────────────────────┐
│  Dashboard users, MCP clients, Diagnostic assistant     │
│  (read-only, scoped to authorized projects)             │
└─────────────────────────────────────────────────────────┘
```

## 5. Data Flow — Happy Path

1. Agent calls `agentops.start_run()` → SDK creates `run_id`, `trace_id`, root span
2. Agent executes LLM/tool calls → SDK/adapter records child spans and events
3. Agent finishes → SDK calls `end_run()`, flushes buffered batch to Ingestion API
4. Ingestion API validates → writes run+events to PostgreSQL, exports spans via OTLP to Tempo, increments Prometheus counters
5. Prometheus scrapes `/metrics` periodically
6. Dashboard/Grafana queries PostgreSQL + Prometheus + Tempo via Query Service
7. MCP client calls `get_run_details` → MCP Server → Query Service → PostgreSQL → structured response
8. Diagnostic assistant receives user question → calls MCP tools → correlates evidence → returns diagnosis

## 6. Storage Responsibility Matrix

| Data | Store | Retention | Notes |
|---|---|---|---|
| Org / project / agent config | PostgreSQL | Permanent | Core registry |
| API keys (hashed) | PostgreSQL | Until rotated | Never stored in plaintext |
| Run metadata | PostgreSQL | Configurable (default 90d) | Searchable, indexed |
| Events (lifecycle) | PostgreSQL | Tied to run retention | Linked to run_id |
| Trace spans | Tempo | Configurable (default 30d) | May expire before run metadata |
| Numeric metrics | Prometheus | Configurable (default 30d) | Aggregates only |
| Dashboard config | Grafana / PostgreSQL | Permanent | Dashboard JSON / settings |
| Secrets / keys | Environment / vault | N/A | Never in DB or telemetry |

## 7. Proposed Repository Structure

```
AgentOpsMCP/
├── sdk/                          # Python SDK package
│   ├── agentops_sdk/
│   │   ├── __init__.py
│   │   ├── client.py             # AgentOps main client
│   │   ├── config.py             # SDK configuration
│   │   ├── context.py            # Run/trace context propagation
│   │   ├── events.py             # Event/span models
│   │   ├── exporters/            # Exporter abstraction + HTTP exporter
│   │   ├── redaction.py          # Redaction hooks
│   │   └── adapters/             # Framework-specific adapters
│   ├── tests/
│   ├── pyproject.toml
│   └── README.md
│
├── backend/                      # FastAPI ingestion + query service
│   ├── agentops_backend/
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI app factory
│   │   ├── config.py             # Backend configuration
│   │   ├── auth/                 # API key auth, tenant scoping
│   │   ├── ingestion/            # Ingestion routes + service
│   │   ├── query/                # Query routes + service
│   │   ├── models/               # SQLAlchemy / DB models
│   │   ├── schemas/              # Pydantic request/response schemas
│   │   ├── metrics/              # Prometheus metric definitions
│   │   ├── tracing/              # OTel trace export config
│   │   └── health.py             # Liveness / readiness
│   ├── migrations/               # Alembic or equivalent
│   ├── tests/
│   ├── pyproject.toml
│   └── README.md
│
├── mcp_server/                   # MCP server (read-only tools)
│   ├── agentops_mcp/
│   │   ├── __init__.py
│   │   ├── server.py             # MCP server setup
│   │   ├── tools/                # Individual tool implementations
│   │   ├── auth.py               # MCP auth + tenant scoping
│   │   └── schemas.py            # Tool input/output schemas
│   ├── tests/
│   ├── pyproject.toml
│   └── README.md
│
├── assistant/                    # AI Diagnostic Assistant
│   ├── agentops_assistant/
│   │   ├── __init__.py
│   │   ├── investigator.py       # Investigation workflow
│   │   ├── prompts.py            # System prompts + response format
│   │   ├── llm_provider.py       # Provider abstraction
│   │   └── safety.py             # Prompt-injection defenses
│   ├── tests/
│   ├── pyproject.toml
│   └── README.md
│
├── dashboard/                    # React + TypeScript frontend
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── README.md
│
├── infra/                        # Docker / infrastructure config
│   ├── docker-compose.yml        # Local development stack
│   ├── grafana/                  # Provisioned dashboards + datasources
│   ├── prometheus/               # prometheus.yml
│   ├── tempo/                    # tempo.yml
│   └── postgres/                 # init scripts
│
├── examples/                     # Example agents + integration demos
│   └── simple_agent.py
│
├── docs/                         # Documentation
│   ├── architecture.md           # ← this file
│   ├── telemetry-schema.md
│   ├── implementation-plan.md
│   ├── testing-strategy.md
│   └── assumptions-and-decisions.md
│
├── .env.example
├── .gitignore
├── AGENTS.md
├── PRD.md
├── PROGRESS.md
├── IMPLEMENTATION_STATUS.md
├── implementation.md
└── README.md
```

## 8. Local Development Stack (Docker Compose)

| Service | Image / Build | Port | Purpose |
|---|---|---|---|
| `backend` | Build `./backend` | 8000 | Ingestion + Query API |
| `postgres` | `postgres:16` | 5432 | Run/event/agent store |
| `prometheus` | `prom/prometheus` | 9090 | Metrics |
| `tempo` | `grafana/tempo` | 3200 (HTTP), 4317 (OTLP gRPC), 4318 (OTLP HTTP) | Traces |
| `grafana` | `grafana/grafana` | 3000 | Dashboards |
| `dashboard` | Build `./dashboard` | 3001 | Product UI |
| `mcp_server` | Build `./mcp_server` | 8001 (or stdio) | MCP tools |
