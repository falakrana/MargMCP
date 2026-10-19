# AgentOps MCP

**Observability and diagnostic platform for AI agents.**

Instrument your AI agents, collect telemetry, monitor metrics, explore traces, search run history, and investigate failures with an AI diagnostic assistant — all through a unified platform with MCP tool access.

---

## What It Does

| Capability | Description |
|---|---|
| **Instrument** | Python SDK + framework adapters with minimal code changes |
| **Collect** | Validated, normalized telemetry ingestion via FastAPI |
| **Observe** | Prometheus metrics + Grafana dashboards |
| **Trace** | Distributed traces via OpenTelemetry + Tempo |
| **Search** | Run history with filters, pagination, error summaries |
| **Query** | Read-only MCP tools for programmatic access |
| **Diagnose** | AI assistant that investigates failures with evidence |

## Project Status

**Phase 6 of 10 — Monitoring Dashboard** → `READY_FOR_REVIEW`

- **Completed & Approved:** Phase 1 (Architecture & Planning), Phase 2 (Core SDK & Instrumentation), Phase 3 (Ingestion API & Persistence), Phase 4 (Metrics, Prometheus, and Trace Export Pipeline), Phase 5 (Trace Details and Run History).
- **Current Phase:** Phase 6 (Monitoring Dashboard) is implemented and ready for human review.

See [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) and [PROGRESS.md](PROGRESS.md) for full details.

## Tech Stack

| Layer | Technology |
|---|---|
| SDK & Backend | Python, FastAPI, Pydantic |
| Database | PostgreSQL (SQLite for tests/local) |
| Metrics | Prometheus |
| Tracing | OpenTelemetry + Grafana Tempo |
| Dashboards | Grafana + React/TypeScript |
| MCP Server | Python MCP SDK |
| AI Assistant | Configurable LLM provider |
| Local Dev | Docker Compose |

## Documentation

- [Architecture](docs/architecture.md)
- [Telemetry Schema](docs/telemetry-schema.md)
- [Observability Guide](docs/observability.md)
- [SDK Integration Guide](docs/sdk-integration-guide.md)
- [Monitoring Dashboard Guide](docs/dashboard.md)
- [Trace & Run History Guide](docs/trace-and-history.md)
- [API Documentation](docs/api.md)
- [Data Model](docs/data-model.md)
- [Implementation Plan](docs/implementation-plan.md)
- [Testing Strategy](docs/testing-strategy.md)
- [Assumptions & Decisions](docs/assumptions-and-decisions.md)
- [PRD / SRS](PRD.md)
- [Implementation Instructions](implementation.md)
- [Progress Log](PROGRESS.md)

## Quick Start

```bash
# Clone and configure
cp .env.example .env
# Edit .env with your values

# Start local development stack (PostgreSQL, Prometheus, Tempo, Grafana)
docker compose -f infra/docker-compose.yml up -d

# Start backend locally
uvicorn agentops_backend.main:app --reload

# Start frontend dashboard (in a separate terminal)
cd frontend
npm install
npm run dev
```

## License

TBD
