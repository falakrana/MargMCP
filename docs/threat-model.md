# AgentOps MCP — Threat Model & Security Architecture Review

## 1. Executive Summary & Purpose

This threat model review analyzes the security posture of the **AgentOps MCP** observability platform following the Phase 9 hardening initiatives. AgentOps is designed to instrument, monitor, and diagnose autonomous AI agents in production environments. Because observability platforms inherently collect system telemetry and operate alongside critical business agents, AgentOps must guarantee:
1. **Zero Monitored Agent Disruption:** A failure, network partition, or degradation in AgentOps must never crash or block business operations.
2. **Strict Multi-Tenant Scoping:** Telemetry, API keys, and diagnostic insights must never cross project boundaries.
3. **Defense Against Secret Leakage:** Prompts, system logs, error messages, metric labels, and LLM diagnostic contexts must never leak sensitive tokens, credentials, or customer PII.
4. **Denial-of-Service Resilience:** Request streams, payload sizes, query windows, pagination offsets, and metric label cardinalities must be strictly bounded.

---

## 2. System Architecture & Trust Boundaries

AgentOps MCP comprises seven primary trust zones separated by explicit security boundaries:

```
+---------------------------------------------------------------------------------------+
| ZONE 1: Untrusted External Environment                                                |
| (External Networks, Monitored Agent Applications, Third-Party LLM Endpoints)          |
+---------------------------------------------------------------------------------------+
                     │                                      │
                     ▼ (OTLP / HTTP Ingest + TLS)           ▼ (REST / SSE + Auth)
+────────────────────────────────────────+  +───────────────────────────────────────────+
| ZONE 2: AgentOps Ingestion & REST API  |  | ZONE 3: Diagnostic Assistant & MCP Server |
| - Rate Limiter (IP & Project Token)    |  | - Read-only tool boundary                 |
| - BodyLimitMiddleware (413 Stream Cap) |  | - Untrusted telemetry prompt sandbox      |
| - Secret Scrubbing & Redaction Engine  |  | - Static code read-only guarantee         |
| - Constant-time Auth (safe_equals)     |  | - Hardened citation validator             |
+────────────────────────────────────────+  +───────────────────────────────────────────+
                     │                                      │
                     ├──────────────────┬───────────────────┤
                     ▼                  ▼                   ▼
+──────────────────────────+  +───────────────────+  +──────────────────────────────────+
| ZONE 4: Relational Store |  | ZONE 5: Metrics   |  | ZONE 6: Trace Backend            |
| - PostgreSQL (RDS/Neon)  |  | - Prometheus      |  | - Grafana Tempo / OTLP           |
| - Parameterized Queries  |  | - In-Memory Series|  | - Tenant-Scraped Traces          |
| - Tenancy WHERE clauses  |  |   Cap (Max 1000)  |  | - TTL Auto-Expiry                |
| - Pooled Connections     |  | - Bounded Labels  |  |                                  |
+──────────────────────────+  +───────────────────+  +──────────────────────────────────+
                     ▲
                     │ (Management & Purge CLI)
+─────────────────────────────────────────────────+
| ZONE 7: Retention & Administrative CLI          |
| - Project-scoped hard deletes                   |
| - Safe dry-run defaults                         |
+─────────────────────────────────────────────────+
```

### Trust Boundaries & Threat Actors
- **Boundary A (Agent SDK -> Ingestion API):** Untrusted payloads over public or internal networks. Threat actors include malicious internal developers, compromised agent processes, or network adversaries.
- **Boundary B (Dashboard / MCP Client -> Query API):** Authenticated users and AI assistants querying run data. Threat actors include unauthorized tenants attempting cross-project access or prompt injection attackers trying to poison diagnostic outputs.
- **Boundary C (Backend -> PostgreSQL / Metrics / Traces):** Internal infrastructure communication. Threat actors include compromised internal services or SQL injection vectors.
- **Boundary D (Diagnostic Assistant -> External LLM Provider):** Outbound queries to hosted LLM endpoints (e.g. Groq, OpenAI). Threat of sensitive payload leakage across external API boundaries.

---

## 3. STRIDE Threat Analysis & Mitigations

### 3.1 Spoofing (Identity & Authentication)

| Threat | Vulnerability / Attack Vector | Implemented Phase 9 Mitigation | Status |
|---|---|---|---|
| **API Key Brute Force** | High-velocity guessing of ingest/read keys. | Token rate limiting via `RateLimiter` (default 600 RPM, burst 100). Hashed token lookups (`HMAC-SHA256`). Minimum token length enforcement (`MIN_TOKEN_LENGTH = 24`). | Mitigated |
| **Surrogate / Timing Side-Channel** | Comparing auth tokens via standard string comparison or malformed Unicode surrogate sequences triggering crashes. | Constant-time byte-level comparison `safe_equals` utilizing UTF-8 byte encoding with `surrogatepass` error handling. | Mitigated |
| **Stale Key Compromise** | Compromised credentials persist indefinitely. | Key rotation API (`POST /v1/projects/{id}/api-keys/rotate`) with atomic dual-key grace periods and explicit revocation (`/revoke`). | Mitigated |
| **Token Homogeneity** | Identical tokens used for Admin, Metrics, and Ingest permissions. | Enforced distinction: `AGENTOPS_SECRET_KEY`, `AGENTOPS_ADMIN_TOKEN`, and `AGENTOPS_METRICS_TOKEN` must be distinct in production. | Mitigated |

### 3.2 Tampering (Data Integrity)

| Threat | Vulnerability / Attack Vector | Implemented Phase 9 Mitigation | Status |
|---|---|---|---|
| **Cross-Tenant Event Injection** | Tenant A attempts to insert events into Tenant B's run ID. | Backend enforces `run.project_id == auth.project_id` and composite primary key constraints `(project_id, event_id)` on all operations. | Mitigated |
| **Idempotency Replay Attacks** | Duplicate or out-of-order events corrupting run status state machine. | Idempotent upserts on `(project_id, event_id)`; state machine allows monotonic transitions only (`running` -> `completed` / `failed`). | Mitigated |
| **Payload Tampering via JSON Injection** | Malformed nested JSON payloads causing parser denial of service or AST memory leaks. | Strict Pydantic v2 validation models, `max_payload_bytes` enforcement, and recursive schema depth limits. | Mitigated |

### 3.3 Repudiation (Auditability)

| Threat | Vulnerability / Attack Vector | Implemented Phase 9 Mitigation | Status |
|---|---|---|---|
| **Unrecorded Administrative Actions** | Secret rotation, telemetry purging, or key revocation occurs without traceability. | Structured JSON logging (`JsonFormatter`) with audit events recording timestamp, action, actor project ID, target ID, and client IP without logging keys. | Mitigated |
| **Trace Disconnect** | Telemetry logs and backend errors cannot be correlated with specific client requests. | `X-Request-ID` generation and propagation middleware linking HTTP request logs to downstream database and diagnostic operations. | Mitigated |

### 3.4 Information Disclosure (Confidentiality)

| Threat | Vulnerability / Attack Vector | Implemented Phase 9 Mitigation | Status |
|---|---|---|---|
| **Credential Leakage in Logs** | Database connection URLs, Bearer tokens, or API keys written to stdout/syslog. | Custom `JsonFormatter` coupled with `scrub_text` sanitizing URLs with passwords (`postgres://user:pass@host`), JWTs, Bearer tokens, `aop_`, `sk-`, and `gsk-` keys. | Mitigated |
| **Metric Label Cardinality Leakage** | Raw prompts, user IDs, or exception strings embedded in Prometheus labels. | Strict whitelist of metric labels; `SeriesCap` class limiting unique label combinations to 1000 per family and grouping excess series into `"other"`. | Mitigated |
| **Prompts in Traces & Storage** | Customer prompts stored by default in traces or database events. | `AGENTOPS_PAYLOAD_CAPTURE_ENABLED=false` by default. SDK and Backend recursive scrubbing removes sensitive fields even when capture is enabled. | Mitigated |
| **Diagnostic Assistant Exfiltration** | An attacker embeds instructions in an agent error to trick the diagnostic LLM into exfiltrating secrets. | Prompt isolation sandboxing (delimited data fences), untrusted data warnings, strict read-only tool verification, and stripping of unrecognized citations. | Mitigated |
| **API Docs Discovery** | Unauthorized users map endpoints via Swagger / OpenAPI UI. | `AGENTOPS_ENABLE_DOCS=false` default in production; `/docs` and `/redoc` disabled. | Mitigated |

### 3.5 Denial of Service (Availability)

| Threat | Vulnerability / Attack Vector | Implemented Phase 9 Mitigation | Status |
|---|---|---|---|
| **Oversized Request Flooding** | Adversary streams gigabyte payloads to exhaust backend memory. | `BodyLimitMiddleware` intercepts streaming chunks and rejects any request exceeding `max_payload_bytes` immediately with HTTP 413. | Mitigated |
| **Database Pool Starvation** | Slow queries or client connection leaks exhaust PostgreSQL pool. | Configured connection pooling (`db_pool_size`, `max_overflow`, `pool_recycle`), connection timeout (10s), and statement timeout (`db_statement_timeout_ms = 15000`). | Mitigated |
| **Deep Pagination / Query Exhaustion** | Heavy queries requesting `limit=1000000` or `offset=9999999` locking table scans. | Hard caps on `offset <= 10000` (`max_page_offset`) and mandatory time window restrictions (`rest_max_window_days = 90`). | Mitigated |
| **SDK Exporter Backpressure Crash** | Agent crashes if AgentOps backend is offline or slow. | SDK `AsyncBatchProcessor` bounded in-memory queue; non-blocking enqueue; drops overflow safely (`dropped_events_count`); all network errors swallowed. | Mitigated |
| **Retry Storms** | Exponential SDK retries synchronizing and hammering a recovering backend. | Bounded exponential backoff (`max_retries = 3`) with randomized jitter; strict adherence to `Retry-After` headers on HTTP 429; fail-fast on 4xx errors. | Mitigated |

### 3.6 Elevation of Privilege (Authorization)

| Threat | Vulnerability / Attack Vector | Implemented Phase 9 Mitigation | Status |
|---|---|---|---|
| **Read Key Ingest Escalation** | Client with `read` key attempts to ingest telemetry or register agents. | Explicit scope enforcement on route dependencies: `require_scope("ingest")` vs `require_scope("read")` vs `require_admin_token()`. | Mitigated |
| **Diagnostic Assistant Command Execution** | Assistant claims to have restarted an agent, executed a remediation script, or altered a database record. | Diagnostic engine verifies tools are read-only; static code tests prove zero write capabilities; action-claim filters strip false remediation statements. | Mitigated |

---

## 4. Sensitive Data Flow Matrix

| Telemetry Element | Origin | Ingestion API | PostgreSQL Store | Prometheus | Tempo (OTLP) | LLM Assistant |
|---|---|---|---|---|---|---|
| **Run ID / Agent ID** | Monitored Agent | Cleartext | Cleartext (Indexed) | Bounded Labels | Cleartext (Span Tag) | Cleartext Context |
| **Event Name / Type** | Monitored Agent | Cleartext | Cleartext | Whitelisted Label | Cleartext (Span Name) | Cleartext Context |
| **API Keys / Bearer Tokens** | Monitored Agent | **Scrubbed** | **Never Stored** | **Never Stored** | **Never Stored** | **Never Sent** |
| **Database Connection Strings** | Monitored Agent | **Scrubbed** | **Never Stored** | **Never Stored** | **Never Stored** | **Never Sent** |
| **Raw Prompts / Payloads** | Monitored Agent | Dropped by default | Dropped by default | **Never Stored** | Dropped by default | Redacted Summaries |
| **Stack Traces / Exceptions** | Monitored Agent | **Scrubbed Text** | Sanitized Summary | Error Type Label Only | Sanitized Status Tag | Redacted Context |

---

## 5. Security Verification & Test Coverage Summary

Phase 9 verified and hardened these protections through dedicated test suites:
- `backend/tests/test_security_phase9.py`: 13 automated tests verifying key rotation, revocation, constant-time `safe_equals`, `BodyLimitMiddleware` 413 rejection, secret scrubbing in JSON logs, rate limiting, and project telemetry purge.
- `backend/tests/test_performance_cardinality.py`: 5 automated tests verifying `SeriesCap` cardinality bounds (1000 cap), pagination depth rejection, query time window capping, database statement timeout configuration, and synthetic batch ingestion latency.
- `sdk/tests/test_sdk_resilience.py`: 6 automated tests validating exponential backoff, jitter, fail-fast on 4xx, `Retry-After` compliance, connection error suppression, queue overflow safety, and unconditional credential redaction.
- `backend/tests/test_assistant.py`: 68 tests confirming prompt injection resilience, citation verification, and read-only enforcement.
