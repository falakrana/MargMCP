# AgentOps MCP — Testing Strategy

## 1. Overview

Testing is organized into five tiers, each with clear scope and tooling.

---

## 2. Test Tiers

### 2.1 Unit Tests

| Component | Scope | Framework |
|---|---|---|
| SDK | Event generation, lifecycle state machine, config parsing, redaction, context propagation, exporter abstraction | `pytest` |
| Backend | Schema validation, service logic, authorization checks, metric recording, query filters, pagination | `pytest` |
| MCP Server | Tool input validation, output formatting, auth checks | `pytest` |
| Assistant | Prompt construction, evidence formatting, safety filters | `pytest` |
| Dashboard | Component rendering, state management, data transformation | `vitest` / `jest` |

**Mocking:** External services (DB, Prometheus, Tempo, LLM) are mocked at the repository/client boundary.

### 2.2 Integration Tests

| Scenario | What It Validates |
|---|---|
| SDK → Ingestion API | SDK payload reaches backend, is validated, and persisted |
| Adapter → Ingestion API | Adapter produces canonical schema, same as SDK |
| Ingestion → PostgreSQL | Runs/events are persisted, queryable, idempotent |
| Ingestion → Prometheus | Metrics increment correctly after ingestion |
| Ingestion → Tempo | Trace spans are exported and retrievable by trace_id |
| Query Service → PostgreSQL + Tempo | Run detail joins metadata + trace spans correctly |
| MCP Server → Query Service | MCP tools return correct data from backend services |
| Dashboard → Backend API | UI data matches API responses |

**Environment:** Uses Docker Compose to spin up PostgreSQL, Prometheus, Tempo for integration tests.

### 2.3 Contract Tests

| Contract | Validated Between |
|---|---|
| Telemetry schema v1 | SDK ↔ Ingestion API |
| API response schemas | Backend ↔ Dashboard |
| MCP tool schemas | MCP Server ↔ MCP Clients |

Schema changes must not silently break consumers.

### 2.4 Security Tests

| Test | Description |
|---|---|
| Auth bypass | Submit telemetry without API key → 401 |
| Cross-project access | Query runs from project B using project A's key → 403 |
| Payload injection | Malformed JSON, oversized payloads, SQL injection attempts → rejected safely |
| Prompt injection | Telemetry containing instructions → treated as data by assistant |
| Credential leakage | Logs, error responses, traces, metrics → no secrets |
| Redaction | Payload capture disabled → no raw prompts in DB/traces |

### 2.5 Performance Tests

| Test | Metric | Tool |
|---|---|---|
| SDK overhead | Latency delta vs. uninstrumented agent | `pytest-benchmark` or manual timing |
| Ingestion throughput | Events/sec sustained | `locust` or `k6` |
| Query latency | p50/p95/p99 for run search, trace retrieval | `locust` or `k6` |
| Prometheus cardinality | Label series count under load | Prometheus TSDB stats |
| MCP tool response time | p95 for each tool | Integration test timing |

---

## 3. Test Execution

| Stage | Tests Run | When |
|---|---|---|
| Local development | Unit + selected integration | Before commit |
| PR / pre-merge | Unit + integration + contract + security | CI (Phase 10) |
| Release candidate | All above + performance + E2E | Pre-release |

---

## 4. Test Data

- **Unit tests:** Inline fixtures and factory functions
- **Integration tests:** Seed data scripts clearly marked as `SYNTHETIC / DEMO DATA`
- **Performance tests:** Parameterized synthetic workloads with documented volume

**Never** use production data, real API keys, or customer content in tests.

---

## 5. Coverage Targets

| Component | Minimum Coverage |
|---|---|
| SDK core | 90% line coverage |
| Backend services | 85% line coverage |
| MCP tools | 85% line coverage |
| Dashboard components | 70% line coverage |

Coverage is a guide, not a substitute for testing meaningful behavior.

---

## 6. Manual Verification

Each phase includes a human verification checklist. These are documented in `implementation.md` and `docs/implementation-plan.md`. Manual checks are required before phase approval.
