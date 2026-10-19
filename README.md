# AgentOps MCP

<div align="center">

**Enterprise-Grade Observability, Distributed Tracing & Diagnostic Intelligence for AI Agents**

[![Phase Status](https://img.shields.io/badge/Phase%206-READY__FOR__REVIEW-blue.svg)](file:///c:/Users/Falak/Desktop/AgentOpsMCP/IMPLEMENTATION_STATUS.md)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](file:///c:/Users/Falak/Desktop/AgentOpsMCP/backend/pyproject.toml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?logo=fastapi)](file:///c:/Users/Falak/Desktop/AgentOpsMCP/backend/agentops_backend/main.py)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react)](file:///c:/Users/Falak/Desktop/AgentOpsMCP/frontend/package.json)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0%2B-3178C6?logo=typescript)](file:///c:/Users/Falak/Desktop/AgentOpsMCP/frontend/tsconfig.json)
[![Vite](https://img.shields.io/badge/Vite-8-646CFF?logo=vite)](file:///c:/Users/Falak/Desktop/AgentOpsMCP/frontend/vite.config.ts)
[![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-Tracing-F5A800?logo=opentelemetry)](file:///c:/Users/Falak/Desktop/AgentOpsMCP/backend/agentops_backend/tracing.py)
[![Prometheus](https://img.shields.io/badge/Prometheus-Metrics-E6522C?logo=prometheus)](file:///c:/Users/Falak/Desktop/AgentOpsMCP/backend/agentops_backend/metrics.py)
[![License](https://img.shields.io/badge/License-Apache--2.0-green.svg)](file:///c:/Users/Falak/Desktop/AgentOpsMCP/README.md)

</div>

---

## Overview

**AgentOps MCP** is an end-to-end observability, distributed tracing, and diagnostic platform purpose-built for AI agents, multi-agent frameworks, and retrieval-augmented generation (RAG) pipelines.

Standard APM tools monitor HTTP servers, database queries, and host resources. They cannot answer the questions that matter when AI agents break:
- *Why did the agent loop 14 times before timing out?*
- *Which specific tool call failed, and did it receive poisoned arguments?*
- *How much latency did vector database retrieval contribute vs. LLM token generation?*
- *Where was memory or context corrupted across multi-step handoffs?*

AgentOps MCP bridges this gap. It captures every agent decision, tool execution, LLM call, and error transition with sub-millisecond precision, providing:
1. **Lightweight Python SDK** with non-blocking async batching and zero-code-change decorators.
2. **High-Throughput Ingestion Engine** with strict schema validation, HMAC-SHA256 authenticated API keys, and isolated project namespaces.
3. **Modern React 19 Monitoring Dashboard** featuring waterfall span trees, real-time KPI metrics, active agent directories, and error diagnostics.
4. **OpenTelemetry & Prometheus Pipeline** with Grafana Tempo trace materialization and pre-provisioned Grafana dashboards.
5. **Model Context Protocol (MCP) Read-Only Toolset & AI Diagnostics** *(Phases 7 & 8)* for autonomous root-cause investigation.

---

## Architecture

```mermaid
flowchart TD
    subgraph ClientApplications["AI Agents & Client Services"]
        Agent["Python AI Agent / LangChain / RAG"]
        SDK["AgentOps SDK (agentops-sdk)"]
        Queue[("Async Batch Queue")]
        Agent -->|@observe_agent / start_run| SDK
        SDK -->|Buffer Events| Queue
    end

    subgraph IngestionPlane["Ingestion & Core API (Port 8000)"]
        FastAPI["FastAPI Ingestion Engine"]
        Auth["HMAC-SHA256 Key & Scope Auth"]
        Validator["Schema v1.0 & Cardinality Gate"]
        DBAccess["SQLAlchemy ORM + Alembic"]
        Queue -->|POST /v1/telemetry/events| FastAPI
        FastAPI --> Auth --> Validator --> DBAccess
    end

    subgraph StorageLayer["Persistence & Database"]
        DB[("PostgreSQL / Neon / SQLite")]
        DBAccess --> DB
    end

    subgraph ObservabilityPlane["Telemetry & Metrics Pipeline"]
        OTel["OpenTelemetry Tracer (Resilient Batch Processor)"]
        Prom["Prometheus Collector (/metrics)"]
        Tempo["Grafana Tempo (OTLP 4318/4317)"]
        PromServer["Prometheus Server (Port 9090)"]
        Grafana["Grafana Dashboards (Port 3000)"]

        FastAPI -->|Post-commit Trace Spans| OTel
        FastAPI -->|Observe Metrics| Prom
        OTel -->|OTLP/HTTP Wire| Tempo
        PromServer -->|Scrape /metrics| Prom
        Grafana -->|Query Datasources| Tempo
        Grafana -->|Query Datasources| PromServer
    end

    subgraph Visualization["UI & Diagnostic Clients"]
        Dashboard["React 19 Dashboard (Port 3001)"]
        MCP["MCP Server Tools (Phase 7)"]
        Assistant["AI Diagnostic Assistant (Phase 8)"]

        Dashboard -->|REST API with Bearer Token| FastAPI
        MCP -->|Read-Only Inspection Tools| FastAPI
        Assistant -->|Investigate Failures| MCP
    end
```

---

## Project Status

The project strictly follows a structured 10-phase engineering workflow defined in [`implementation.md`](file:///c:/Users/Falak/Desktop/AgentOpsMCP/implementation.md).

| Phase | Description | Status | Evidence & Test Suite |
|---|---|---|---|
| **Phase 1** | Repository Discovery, Architecture & Implementation Plan | `APPROVED` | [`docs/architecture.md`](file:///c:/Users/Falak/Desktop/AgentOpsMCP/docs/architecture.md), [`docs/telemetry-schema.md`](file:///c:/Users/Falak/Desktop/AgentOpsMCP/docs/telemetry-schema.md) |
| **Phase 2** | Core SDK & First Instrumentation Adapter | `APPROVED` | `sdk/agentops_sdk/` (3 tests, non-blocking queue, redaction) |
| **Phase 3** | Ingestion API, Persistence & Query Services | `APPROVED` | `backend/agentops_backend/` (89 tests, HMAC auth, migrations) |
| **Phase 4** | Metrics, Prometheus & Trace Export Pipeline | `APPROVED` | OpenTelemetry OTLP export, Prometheus `/metrics` (134 tests) |
| **Phase 5** | Trace Details & Run History | `APPROVED` | Waterfall timeline engine, correlation links (172 tests total) |
| **Phase 6** | **Monitoring Dashboard** | `READY_FOR_REVIEW` | **React 19 + TypeScript + Vite UI (20 frontend tests, 0 lint errors)** |
| **Phase 7** | MCP Server & Read-Only Monitoring Tools | `NOT_STARTED` | Tool schemas defined in PRD §6; begins upon Phase 6 approval |
| **Phase 8** | AI Diagnostic Assistant | `NOT_STARTED` | Evidence-based diagnostic loop; begins upon Phase 7 approval |
| **Phase 9** | Security, Reliability & Performance Hardening | `NOT_STARTED` | Rate limiting, fuzz testing, chaos resilience |
| **Phase 10**| Deployment, End-to-End Pilot & Release Readiness | `NOT_STARTED` | Production containers, CI/CD, documentation polish |

*For historical session logs and complete audit trails, see [`PROGRESS.md`](file:///c:/Users/Falak/Desktop/AgentOpsMCP/PROGRESS.md) and [`IMPLEMENTATION_STATUS.md`](file:///c:/Users/Falak/Desktop/AgentOpsMCP/IMPLEMENTATION_STATUS.md).*

---

## Core Capabilities

### 1. Zero-Overhead Python SDK (`agentops-sdk`)
- **Non-blocking asynchronous delivery**: Background batch worker buffers events in an in-memory queue and flushes every 2 seconds. Telemetry outages never crash or stall monitored agents.
- **Gradual adoption model**:
  - **Level 1 (`@observe_agent`)**: Automatic lifecycle, execution duration, and exception tracking via a single decorator.
  - **Level 2 (`with agentops.start_run()`)**: Context manager for orchestrating multi-step pipelines and tagging metadata.
  - **Level 3 (Fine-grained spans)**: Record granular tool execution times, vector search retrieval latencies, and LLM token usage.
- **Privacy by default**: Automatic redaction of sensitive keys (`prompt`, `secret`, `api_key`, `credentials`) before leaving the client.

### 2. High-Performance Ingestion & Query Engine (FastAPI)
- **Strict schema validation**: Enforces Telemetry Schema v1.0, sub-second timestamp bounded within ±24 hours, and strict identifier validation.
- **Idempotency & out-of-order convergence**: `(project_id, event_id)` idempotency guarantees duplicate retries are safe. Out-of-order events converge into accurate run durations and statuses.
- **Project boundary isolation**: Every query, run record, and event is strictly partitioned by `project_id`. Cross-project leaks are rejected at the ORM layer.
- **HMAC-SHA256 authenticated API keys**: Plaintext keys are generated once, hashed, and never stored or logged.

### 3. Modern React 19 Monitoring Dashboard (`frontend/`)
- Built with **React 19, TypeScript, Vite 8, React Query v5, and Recharts**.
- Designed with a clean, **minimalist whitish theme** (`#ffffff` canvas, `#f8fafc` subtle background, `#e2e8f0` slate borders, and `#4f46e5` indigo accent).
- **7 Fully Integrated Pages**:
  - 📊 **Overview Dashboard (`/`)**: KPI summary cards (Total Runs, Success Rate %, Latency, Token Consumption, Active Agents), 24h volume area chart, latency distribution, and recent activity feed.
  - 🤖 **Agents Directory (`/agents` & `/agents/:agentId`)**: Registered agent roster with runtime metrics, error frequencies, and direct filtered run histories.
  - 📜 **Run History (`/runs`)**: Searchable, paginated execution ledger with status, environment, and agent filters.
  - 🌲 **Run Detail & Waterfall Span Tree (`/runs/:runId`)**: Hierarchical span waterfall visualizing tool and LLM latencies, expandable JSON event stream, and correlation deep links.
  - 🔍 **Trace Explorer (`/traces`)**: Fast OTLP trace-to-run resolution with redirect lookups.
  - ⚠️ **Errors & Diagnostics (`/errors`)**: Aggregated failure signatures grouped by error type with one-click drill-downs into affected runs.
  - ⚙️ **Settings & Connectivity (`/settings`)**: Project API credentials, live backend health checks (`/health/live`, `/health/ready`), privacy posture indicators, and SDK code snippets.

### 4. Distributed Tracing & Observability Pipeline
- **OpenTelemetry trace materialization**: Backend synthesizes root spans (`agent.run`) and child spans (`llm.chat`, `tool.<name>`) directly from ingested events and exports them to Grafana Tempo via OTLP/HTTP.
- **Error-preserving sampling**: Error runs are always exported (100%), while healthy runs follow a configurable sampling ratio (`AGENTOPS_TRACE_SAMPLE_RATIO`).
- **Prometheus metrics**: Exposes bounded, privacy-screened operational metrics (`agentops_runs_total`, `agentops_run_duration_seconds`, `agentops_llm_calls_total`, etc.) via authenticated `GET /metrics`.
- **Pre-configured Grafana dashboards**: Ready-to-use Grafana dashboard provisioning for run rates, error ratios, latency percentiles (p50/p95), and token consumption.

---

## Tech Stack

| Layer | Technologies |
|---|---|
| **Python SDK** | Python 3.10+, Pydantic v2, HTTPX, Requests |
| **Backend & Ingestion** | FastAPI, Uvicorn, SQLAlchemy 2.0, Alembic, Pydantic Settings |
| **Frontend Dashboard** | React 19, TypeScript 5, Vite 8, TanStack Query v5, React Router v7, Recharts, Lucide Icons |
| **Database** | PostgreSQL 16 (Neon Cloud / Local Docker) / SQLite (tests & local dev) |
| **Metrics & TSDB** | Prometheus 2.55+ with custom Python Collector Registry |
| **Distributed Tracing** | OpenTelemetry SDK 1.27+, Grafana Tempo 2.6+ (OTLP 4317 gRPC / 4318 HTTP) |
| **Visualization** | Native React Dashboard + Pre-provisioned Grafana 11.3+ |
| **Orchestration** | Docker Compose, PowerShell, Bash |

---

## Quick Start Guide

### Prerequisites
- **Python**: Version 3.10 or higher
- **Node.js**: Version 18.x or higher (with npm)
- **Docker & Docker Compose**: Optional (required only for local Tempo/Prometheus/Grafana stack)

---

### Step 1: Environment Setup

Clone the repository and copy the environment template:
```bash
cp .env.example .env
```

Edit `.env` to configure your settings (or use the provided developer defaults):
```env
AGENTOPS_ENV=development
AGENTOPS_SECRET_KEY=dev-secret-key-at-least-32-chars-long!
AGENTOPS_ADMIN_TOKEN=dev-admin-token-12345
AGENTOPS_METRICS_TOKEN=dev-metrics-token-12345
DATABASE_URL=sqlite:///./agentops_dev.db
```

---

### Step 2: Start the Backend API

Initialize the virtual environment and install backend dependencies:
```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install backend dependencies in editable mode
pip install -e "backend[dev]"
pip install -e "sdk[dev]"

# Run database migrations
cd backend
alembic upgrade head
cd ..

# Start the FastAPI application
python .\backend\agentops_backend\main.py
```
The backend API is now running at `http://localhost:8000`.
- Interactive Swagger docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health endpoints: [http://localhost:8000/health/live](http://localhost:8000/health/live) and [http://localhost:8000/health/ready](http://localhost:8000/health/ready)

---

### Step 3: Start the Monitoring Dashboard

In a new terminal window:
```bash
cd frontend
npm install
npm run dev
```
Open your browser at **`http://localhost:3001`**.

*When prompted on first load:*
1. Enter your **Project ID**: `default` (or any project you create).
2. Enter your **API Key**: If running in local development with default seed, enter your key or create one via the admin endpoint.

---

### Step 4: Seed Synthetic Demo Data (Optional)

To immediately populate the dashboard with realistic agent runs, tool calls, token metrics, and error scenarios:
```powershell
.\.venv\Scripts\python -m agentops_backend.seed
```
Refresh your browser at `http://localhost:3001` to view live charts, waterfall traces, and error summaries!

---

### Step 5: Start Local Observability Stack (Optional)

To run the full stack including Grafana, Prometheus, and Grafana Tempo:
```bash
docker compose -f infra/docker-compose.yml up -d
```
- **Grafana UI**: [http://localhost:3000](http://localhost:3000) (admin / password in `.env`)
- **Prometheus UI**: [http://localhost:9090](http://localhost:9090)
- **Tempo OTLP Receiver**: `http://localhost:4318` (HTTP) / `localhost:4317` (gRPC)

---

## SDK Integration Guide

Integrating AgentOps into any Python AI agent takes less than 3 minutes.

### 1. Minimal 1-Line Decorator (`@observe_agent`)

```python
from agentops_sdk import AgentOps
from agentops_sdk.adapters.decorator import observe_agent

# Initialize client from environment (.env)
agentops = AgentOps.from_env()

@observe_agent(agentops, agent_id="research-analyst")
def process_user_query(query: str):
    # Your agent execution logic remains 100% untouched
    response = my_llm_chain.invoke(query)
    return response
```

### 2. Context Manager (`with agentops.start_run()`)

```python
from agentops_sdk import AgentOps

agentops = AgentOps.from_env()

def run_agent_workflow(task_payload):
    with agentops.start_run(agent_id="support-bot") as run:
        result = execute_support_workflow(task_payload)
        
        # Attach safe output summary
        run.set_output_summary({"ticket_id": 4829, "resolution": "completed"})
        return result
```

### 3. Fine-Grained Span Tracking (RAG & Tools)

Capture individual retrieval and tool execution latencies to render nested waterfall bars in the dashboard:

```python
import time
from agentops_sdk import AgentOps

agentops = AgentOps.from_env()

async def run_rag_pipeline(query: str):
    with agentops.start_run(agent_id="rag-knowledge-agent") as run:
        # 1. Track Vector Database Retrieval
        t0 = time.perf_counter()
        docs = await vector_store.asimilarity_search(query, k=4)
        retrieval_ms = (time.perf_counter() - t0) * 1000.0

        run.record_event("tool_call_completed", {
            "tool_name": "vector_store_retrieval",
            "duration_ms": retrieval_ms,
            "chunks_retrieved": len(docs)
        })

        # 2. Track LLM Generation
        t0_llm = time.perf_counter()
        answer = await llm.ainvoke([SystemMessage("Answer:"), HumanMessage(query)])
        llm_ms = (time.perf_counter() - t0_llm) * 1000.0

        run.record_event("llm_call_completed", {
            "provider": "anthropic",
            "model": "claude-3-5-sonnet-20241022",
            "duration_ms": llm_ms,
            "prompt_tokens": 420,
            "completion_tokens": 165
        })

        return answer
```

*For complete integration patterns and framework adapters, see the [SDK Integration Guide](file:///c:/Users/Falak/Desktop/AgentOpsMCP/docs/sdk-integration-guide.md).*

---

## Repository Structure

```
AgentOpsMCP/
├── backend/                        # FastAPI Ingestion, Persistence & Queries
│   ├── agentops_backend/
│   │   ├── main.py                 # Application factory & CORS configuration
│   │   ├── routes.py               # Ingestion, Query, Admin & Health routes
│   │   ├── ingestion.py            # Telemetry validation & idempotent persistence
│   │   ├── trace_service.py        # Run timeline & synthetic span assembly
│   │   ├── metrics.py              # Prometheus metrics with cardinality bounding
│   │   ├── tracing.py              # OpenTelemetry span materialization
│   │   ├── auth.py                 # HMAC-SHA256 API key verification
│   │   ├── models.py               # SQLAlchemy relational schemas
│   │   ├── schemas.py              # Pydantic contract schemas
│   │   └── seed.py                 # Synthetic dataset generator
│   ├── migrations/                 # Alembic migration scripts
│   └── tests/                      # 172 unit, integration & contract tests
├── frontend/                       # React 19 + TypeScript Monitoring Dashboard
│   ├── src/
│   │   ├── App.tsx                 # Route declarations & main application shell
│   │   ├── api.ts                  # Typed API client with session Bearer auth
│   │   ├── index.css               # Minimalist design system tokens & styles
│   │   ├── components/             # Reusable UI library (StatusBadge, StatCard, Sidebar)
│   │   ├── context/AuthContext.tsx # Project ID & API key session management
│   │   ├── pages/                  # 7 Core Pages (Overview, Agents, Runs, Detail, Traces, Errors, Settings)
│   │   └── utils.test.ts           # Vitest unit test suite (20 tests passed)
│   ├── package.json
│   └── vite.config.ts
├── sdk/                            # Python Instrumentation SDK (agentops-sdk)
│   ├── agentops_sdk/
│   │   ├── client.py               # AgentOps client & Run context manager
│   │   ├── context.py              # ContextVar runtime propagation
│   │   ├── events.py               # Canonical TelemetryEvent Pydantic model
│   │   ├── redaction.py            # Sensitive data screening pipeline
│   │   ├── adapters/decorator.py   # Zero-overhead @observe_agent decorator
│   │   └── exporters/batch.py      # Non-blocking async background worker
│   └── tests/                      # SDK unit & failure isolation tests
├── infra/                          # Local Observability Infrastructure
│   ├── docker-compose.yml          # PostgreSQL, Prometheus, Tempo & Grafana
│   ├── prometheus/                 # Prometheus scrape configuration
│   ├── tempo/                      # Grafana Tempo OTLP receiver configuration
│   └── grafana/                    # Pre-provisioned datasources & dashboards
└── docs/                           # Architecture, API & Engineering Specifications
    ├── architecture.md             # System boundaries, data flow & security model
    ├── telemetry-schema.md         # Canonical Telemetry Schema v1.0
    ├── dashboard.md                # Phase 6 Frontend Dashboard documentation
    ├── trace-and-history.md        # Span assembly, correlation links & retention
    ├── sdk-integration-guide.md    # Developer integration patterns (Decorator/Context)
    ├── api.md                      # REST API endpoints, payloads & error codes
    ├── observability.md            # Prometheus metrics catalog & OTel guide
    ├── data-model.md               # Relational database entities & index strategy
    ├── implementation-plan.md      # 10-Phase detailed implementation roadmap
    └── testing-strategy.md         # 5-Tier quality assurance framework
```

---

## Testing & Quality Assurance

AgentOps enforces strict automated testing at every phase. Mocks are never represented as production functionality, and all telemetry failure paths are tested to guarantee client resilience.

### Running Backend Tests (Pytest)
```powershell
.\.venv\Scripts\pytest backend/tests -v
```
- **Coverage**: 172 tests covering authentication, idempotent ingestion, time-window boundaries, error-preserving trace sampling, span assembly, and cross-tenant isolation (95% code coverage).

### Running Frontend Tests (Vitest)
```bash
cd frontend
npm run test
```
- **Pass rate**: 20 tests verifying API client query parameter encoding, Bearer token authorization headers, error status envelopes, and utility formatting functions.

### Running Frontend Type Check & Production Build
```bash
cd frontend
npm run build
```
- Sub-second production compilation (`vite build`) with **zero TypeScript errors**.

---

## Security & Privacy Guarantees

1. **Zero Prompt/Secret Leakage**:
   - Raw user prompts, completions, and sensitive tool arguments are **never captured by default** (`AGENTOPS_PAYLOAD_CAPTURE_ENABLED=false`).
   - The SDK automatically screens and strips blacklisted keys (`prompt`, `api_key`, `secret`, `credentials`) before event dispatch.
2. **Cardinality Bounding**:
   - Metric labels are strictly bounded and sanitized. High-cardinality attributes like `run_id`, `trace_id`, user IDs, raw prompts, or exception strings are strictly barred from Prometheus metric labels to prevent TSDB memory exhaustion.
3. **Session-Only Credential Storage**:
   - The web dashboard stores project API keys strictly in browser `sessionStorage`. Keys are never written to `localStorage`, cookies, or baked into build artifacts.
4. **Resilient Failure Boundaries**:
   - Observability outages or network latency never bubble into or interrupt monitored AI agents. The SDK catches all export failures gracefully.

---

## Documentation Index

- **System Architecture**: [`docs/architecture.md`](file:///c:/Users/Falak/Desktop/AgentOpsMCP/docs/architecture.md)
- **Telemetry Schema Specification**: [`docs/telemetry-schema.md`](file:///c:/Users/Falak/Desktop/AgentOpsMCP/docs/telemetry-schema.md)
- **SDK Developer Integration Guide**: [`docs/sdk-integration-guide.md`](file:///c:/Users/Falak/Desktop/AgentOpsMCP/docs/sdk-integration-guide.md)
- **Monitoring Dashboard Guide**: [`docs/dashboard.md`](file:///c:/Users/Falak/Desktop/AgentOpsMCP/docs/dashboard.md)
- **Trace Details & Run History**: [`docs/trace-and-history.md`](file:///c:/Users/Falak/Desktop/AgentOpsMCP/docs/trace-and-history.md)
- **Observability & Metrics Reference**: [`docs/observability.md`](file:///c:/Users/Falak/Desktop/AgentOpsMCP/docs/observability.md)
- **REST API Reference**: [`docs/api.md`](file:///c:/Users/Falak/Desktop/AgentOpsMCP/docs/api.md)
- **Relational Data Model**: [`docs/data-model.md`](file:///c:/Users/Falak/Desktop/AgentOpsMCP/docs/data-model.md)
- **Implementation Plan & Checklist**: [`docs/implementation-plan.md`](file:///c:/Users/Falak/Desktop/AgentOpsMCP/docs/implementation-plan.md)
- **Testing & Verification Strategy**: [`docs/testing-strategy.md`](file:///c:/Users/Falak/Desktop/AgentOpsMCP/docs/testing-strategy.md)
- **Assumptions & Architecture Decisions**: [`docs/assumptions-and-decisions.md`](file:///c:/Users/Falak/Desktop/AgentOpsMCP/docs/assumptions-and-decisions.md)
- **Product Requirements Document (PRD)**: [`PRD.md`](file:///c:/Users/Falak/Desktop/AgentOpsMCP/PRD.md)
- **Work Session Progress Log**: [`PROGRESS.md`](file:///c:/Users/Falak/Desktop/AgentOpsMCP/PROGRESS.md)
- **Implementation Snapshot**: [`IMPLEMENTATION_STATUS.md`](file:///c:/Users/Falak/Desktop/AgentOpsMCP/IMPLEMENTATION_STATUS.md)

---

## License

This project is licensed under the Apache License 2.0. See [`LICENSE`](file:///c:/Users/Falak/Desktop/AgentOpsMCP/LICENSE) for details.
