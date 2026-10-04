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

**Phase 1 of 10 — Architecture & Planning** → `READY_FOR_REVIEW`

See [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for current state.

## Tech Stack

| Layer | Technology |
|---|---|
| SDK & Backend | Python, FastAPI, Pydantic |
| Database | PostgreSQL |
| Metrics | Prometheus |
| Tracing | OpenTelemetry + Grafana Tempo |
| Dashboards | Grafana + React/TypeScript |
| MCP Server | Python MCP SDK |
| AI Assistant | Configurable LLM provider |
| Local Dev | Docker Compose |

## Documentation

- [Architecture](docs/architecture.md)
- [Telemetry Schema](docs/telemetry-schema.md)
- [Implementation Plan](docs/implementation-plan.md)
- [Testing Strategy](docs/testing-strategy.md)
- [Assumptions & Decisions](docs/assumptions-and-decisions.md)
- [PRD / SRS](PRD.md)
- [Implementation Instructions](implementation.md)
- [Progress Log](PROGRESS.md)

## Quick Start

> ⚠️ No runnable code yet — currently in architecture/planning phase.

```bash
# Clone and configure
cp .env.example .env
# Edit .env with your values

# (Future) Start local development stack
docker compose up -d
```

## License

TBD
