# Marg MCP — Assumptions and Decisions Register

> Record every material assumption and decision with date, rationale, alternatives considered, and impact. Mark status as `PROVISIONAL`, `DECIDED`, or `SUPERSEDED`.

---

## Decisions

| #     | Date       | Decision                                                              | Rationale                                                                                                                            | Alternatives Considered                     | Status      |
| ----- | ---------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------- | ----------- |
| D-001 | 2026-10-04 | **Python** is the first SDK and backend language                | PRD specifies Python SDK; team expertise; LLM agent ecosystem is Python-heavy                                                        | TypeScript, Go                              | DECIDED     |
| D-002 | 2026-10-04 | **FastAPI** for the backend ingestion + query API               | PRD recommendation; async support; Pydantic native validation; good OTel integration                                                 | Flask, Django, aiohttp                      | DECIDED     |
| D-003 | 2026-10-04 | **PostgreSQL** for run metadata, events, agent/project registry | PRD lists PostgreSQL as acceptable; strong relational querying for run history search, filtering, pagination; Alembic for migrations | MongoDB (implementation.md default), SQLite | DECIDED     |
| D-004 | 2026-10-04 | **Prometheus** for numeric time-series metrics                  | PRD requirement; industry standard; Grafana-native datasource                                                                        | InfluxDB, Victoria Metrics                  | DECIDED     |
| D-005 | 2026-10-04 | **Grafana Tempo** for distributed trace storage                 | PRD recommendation; OTel-native; integrates with Grafana; free/OSS                                                                   | Jaeger, Zipkin, Elasticsearch               | PROVISIONAL |
| D-006 | 2026-10-04 | **React + TypeScript** for the monitoring dashboard             | implementation.md recommendation; modern SPA ecosystem                                                                               | Vue, Svelte, server-rendered                | PROVISIONAL |
| D-007 | 2026-10-04 | **Docker Compose** for local development                        | PRD requirement for reproducible local dev; keeps infra self-contained                                                               | Podman, Kubernetes dev                      | DECIDED     |
| D-008 | 2026-10-04 | **Single-tenant MVP** with tenant scoping built in from day one | PRD leaves multi-tenant as open; safer to build tenant_id into schemas now and run single-tenant initially                           | Skip tenant concept entirely                | PROVISIONAL |
| D-009 | 2026-10-04 | **Payload capture OFF by default**                              | PRD NFR-04; privacy-first; opt-in with redaction support                                                                             | Capture by default with opt-out             | DECIDED     |
| D-010 | 2026-10-04 | **Diagnostic assistant is read-only** in MVP                    | PRD FR-09; no production mutations                                                                                                   | Allow limited writes                        | DECIDED     |

---

## Assumptions

| #     | Date       | Assumption                                                                                                                                | Impact if Wrong                                                                    | Status      |
| ----- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ----------- |
| A-001 | 2026-10-04 | The first framework adapter will be a**generic Python decorator/context-manager** (not tied to a specific framework like LangChain) | Would need to adjust adapter interface if a specific framework is mandated first   | PROVISIONAL |
| A-002 | 2026-10-04 | **OTLP gRPC** is the primary trace export protocol                                                                                  | Would need HTTP-only fallback if gRPC is blocked in target environments            | PROVISIONAL |
| A-003 | 2026-10-04 | MVP targets**< 100 agents**, **< 50 runs/sec** sustained ingestion                                                            | Architecture decisions around queuing, sharding, etc. would change at higher scale | PROVISIONAL |
| A-004 | 2026-10-04 | **No external queue** (Redis, Kafka) needed for MVP ingestion                                                                       | Would need to add if ingestion throughput exceeds direct-write capacity            | PROVISIONAL |
| A-005 | 2026-10-04 | Default retention:**runs 90 days**, **traces 30 days**, **metrics 30 days**                                             | Storage costs; may need adjustment                                                 | PROVISIONAL |
| A-006 | 2026-10-04 | Dashboard authentication uses**JWT/session tokens** against the backend API                                                         | Would change if an external IdP (OAuth2/OIDC) is required                          | PROVISIONAL |
| A-007 | 2026-10-04 | The diagnostic assistant LLM provider is**configurable via env vars** (default: OpenAI)                                             | Would need a plugin system if many providers must be supported simultaneously      | PROVISIONAL |
| A-008 | 2026-10-04 | **No CI/CD pipeline** is defined yet; will be established in Phase 10                                                               | Earlier phases rely on local test execution                                        | PROVISIONAL |

---

## Open Questions (Requiring Owner Input)

| #     | Question                                                                                      | Default if no answer                      | Priority |
| ----- | --------------------------------------------------------------------------------------------- | ----------------------------------------- | -------- |
| Q-001 | Which specific agent framework adapter to build first? (LangChain, CrewAI, AutoGen, generic?) | Yes langchain or Generic Python decorator | Phase 2  |
| Q-002 | Is the MVP single-tenant or must multi-tenant isolation be demonstrable?                      | Single-tenant with tenant_id in schemas   | Phase 3  |
| Q-003 | Which LLM provider/model for the diagnostic assistant?                                        | Groq models                               | Phase 8  |
| Q-004 | Target deployment: self-hosted Docker only, or cloud (AWS/GCP/Azure)?                         | Docker Compose local only                 | Phase 10 |
| Q-005 | Notification channels for alerts (Slack, email, PagerDuty)?                                   | Dashboard-only in MVP (P1 feature)        | Post-MVP |
