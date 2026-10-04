# AgentOps MCP

## Product Requirements Document (PRD) & Software Requirements Specification (SRS)

**Version:** 0.2 — Refined Draft
**Date:** October 2, 2026
**Status:** Proposed — Pending architecture and scope validation

---

# 1. Executive Summary

AgentOps MCP is an observability and diagnostic platform for AI agents running in development, staging, and production environments.

It provides a standardized way to collect agent telemetry through SDKs and wrappers/adapters, monitor operational metrics, inspect detailed execution traces, search historical runs, and investigate failures through a dedicated AI diagnostic assistant.

The platform combines:

* **Instrumentation:** SDKs and adapters for different agent frameworks and deployment environments.
* **Metrics:** Latency, throughput, errors, token usage, and tool-call statistics.
* **Distributed tracing:** Detailed execution timelines across agent runs, LLM calls, and tool calls.
* **Run history:** Searchable records of individual agent executions.
* **Monitoring:** Prometheus-backed metrics and Grafana dashboards.
* **MCP interface:** Read-only tools for MCP-compatible clients to query observability data.
* **AI diagnostics:** A dedicated assistant that uses monitoring tools to investigate failures and explain findings with supporting evidence.

The goal is to make production AI agents observable and diagnosable without requiring every application team to build its own monitoring infrastructure.

## 1.1 Product Vision

Enable developers and operations teams to answer:

1. Is my AI agent healthy?
2. How many runs are succeeding or failing?
3. Why did a particular run fail?
4. Which LLM call or tool call caused the delay?
5. How are latency, errors, and token usage changing over time?
6. What evidence supports a suspected root cause?
7. Can an AI assistant investigate these questions using the same observability data?

## 1.2 Core Product Principle

AgentOps MCP should separate **telemetry collection, telemetry storage, visualization, and AI-powered investigation** into distinct components.

This prevents the platform from becoming tightly coupled to one agent framework, one LLM provider, or one user interface.

---

# 2. Problem Statement

AI agents can involve multiple LLM calls, tool invocations, retrieval operations, external APIs, and conditional execution paths. When a production run fails or becomes slow, the application logs alone may not provide enough context to understand what happened.

Teams may also lack a consistent way to compare agent behavior across frameworks and deployments.

AgentOps MCP addresses these problems by standardizing telemetry and correlating metrics, traces, and run history through a common observability layer.

# 3. Goals and Non-Goals

## 3.1 Goals

* Support both direct SDK instrumentation and wrappers/adapters.
* Define a common telemetry schema across supported integrations.
* Collect and query metrics, detailed traces, and run history.
* Provide operational dashboards and configurable alerts.
* Expose read-only observability tools through MCP.
* Provide a dedicated AI diagnostic assistant.
* Correlate individual runs with trace spans, errors, and aggregated metrics.
* Support secure deployment with configurable authentication and access controls.
* Keep integrations extensible so new frameworks can be supported incrementally.

## 3.2 Non-Goals for the MVP

* Automatically modifying or repairing production agents.
* Replacing the agent's existing runtime, orchestration framework, or model provider.
* Training or fine-tuning foundation models.
* Replacing general-purpose application logging platforms.
* Supporting every agent framework and programming language at launch.
* Guaranteeing root-cause identification for every failure.
* Automatically executing remediation actions in production.

The diagnostic assistant will be read-only in the MVP. It may suggest remediation steps, but it will not apply them automatically.

---

# 4. Target Users

| User                | Primary need                                          |
| ------------------- | ----------------------------------------------------- |
| AI/ML engineer      | Instrument an agent and inspect individual runs       |
| Backend developer   | Integrate an existing agent with minimal code changes |
| Platform engineer   | Deploy and manage the observability infrastructure    |
| DevOps/SRE engineer | Monitor latency, failures, availability, and alerts   |
| Technical lead      | Compare reliability and usage across agents           |
| Operations engineer | Investigate incidents using the diagnostic assistant  |

# 5. Key User Journeys

## 5.1 Integrating a New Agent

1. A developer creates an AgentOps project or configures an existing deployment.
2. They choose the SDK or an appropriate wrapper/adapter.
3. They configure the AgentOps endpoint and credentials.
4. Their agent begins emitting standardized telemetry.
5. AgentOps records metrics, traces, and run metadata.
6. The agent becomes visible in the monitoring interface.

## 5.2 Monitoring an Agent

1. An operator opens Grafana.
2. They select an agent and environment.
3. They inspect run volume, error rates, latency, and token usage.
4. They identify a time window or metric anomaly.
5. They open associated traces or run-history records for investigation.

## 5.3 Investigating a Failed Run

1. A user asks the diagnostic assistant to investigate a failed run.
2. The assistant queries AgentOps MCP tools.
3. It retrieves the run summary, relevant spans, errors, and surrounding execution context.
4. It correlates the evidence.
5. It returns a diagnosis with supporting trace IDs, timestamps, and relevant observations.
6. It distinguishes observed facts from hypotheses and suggested next steps.

## 5.4 Using an Existing MCP Client

1. A user connects an MCP-compatible client to the AgentOps MCP server.
2. The client discovers available monitoring tools.
3. The user requests metrics, trace details, or run history.
4. The MCP server authorizes the request and retrieves relevant data.
5. The client presents the result.

---

# 6. Proposed System Architecture

## 6.1 High-Level Architecture

```text
                 AI Agent Applications
                          |
             +------------+------------+
             |                         |
        AgentOps SDK              Wrappers / Adapters
             |                         |
             +------------+------------+
                          |
                  Telemetry Pipeline
                          |
                 Ingestion / Collector
                          |
           +--------------+--------------+
           |              |              |
        Metrics          Traces        Run Metadata
           |              |              |
       Prometheus       Trace Store    Run History DB
           |              |              |
           +--------------+--------------+
                          |
                 Query / Service Layer
                          |
             +------------+-------------+
             |                          |
        Grafana UI                 AgentOps MCP
                                        |
                              +---------+---------+
                              |                   |
                        MCP Clients       Diagnostic Assistant
```

The diagram represents logical components, not a requirement to deploy every component as a separate service.

## 6.2 Component Responsibilities

### A. AgentOps SDK

The SDK is used when developers can modify the agent's code.

Responsibilities:

* Provide simple initialization and configuration.
* Capture agent-run lifecycle events.
* Instrument LLM and tool calls where supported.
* Propagate trace context across supported operations.
* Record errors, durations, and usage metadata.
* Support asynchronous execution.
* Send telemetry without unnecessarily blocking agent execution.
* Apply configurable redaction before telemetry leaves the application.

### B. Wrappers and Adapters

Wrappers and adapters integrate existing agents or frameworks with minimal application changes.

Potential integration patterns include:

* Decorators around agent execution functions.
* Middleware around framework execution.
* Callbacks for LLM and tool lifecycle events.
* HTTP or API wrappers for services that cannot use the SDK directly.
* OpenTelemetry-compatible instrumentation adapters.

**Design requirement:** wrappers must use the same canonical telemetry model as the SDK. They should not introduce a separate data format or a different query experience.

The exact frameworks supported in the MVP remain to be decided.

### C. Telemetry Ingestion and Collector

The ingestion layer accepts telemetry from SDKs and adapters.

Responsibilities:

* Validate incoming events and spans.
* Authenticate the sending application.
* Normalize framework-specific fields.
* Attach agent, environment, and deployment metadata.
* Handle duplicate or malformed events safely.
* Route metrics, traces, and run metadata to their respective storage systems.
* Apply rate limits and bounded buffering.
* Report ingestion health and dropped telemetry.

The collector should not be responsible for performing AI diagnosis.

### D. Metrics Storage — Prometheus

Prometheus stores and queries aggregated operational metrics.

Examples:

* Agent runs per minute.
* Successful and failed run counts.
* Run latency distributions.
* LLM and tool-call latency.
* Token usage and associated counts.
* Telemetry ingestion failures.

Prometheus is appropriate for time-series aggregation, but it should not be treated as the primary database for individual execution records or full traces.

### E. Trace Storage

The proposed MVP design uses **OpenTelemetry-compatible traces**, with Grafana Tempo as the initial trace backend.

A trace represents an execution or correlated workflow. Spans represent operations within it, such as:

* Agent run.
* LLM request.
* Tool invocation.
* Retrieval operation.
* External API request.
* Retry or error-handling operation.

Each span should capture relevant timing, status, parent-child relationships, and safe metadata.

Tempo is a proposed implementation choice, not a mandatory product requirement. The architecture should isolate the trace backend behind a query/service layer.

### F. Run History Database

A searchable database stores run-level records and metadata.

The initial proposal is PostgreSQL.

A run record may contain:

* Run ID and agent ID.
* Environment and deployment version.
* Start and end timestamps.
* Overall status and duration.
* Error category and sanitized error summary.
* Trace ID.
* Token and operation summaries where available.
* Selected metadata for filtering.

Detailed span timelines remain in the trace backend. The run database should store a reference to the trace rather than duplicating every span.

This separation supports efficient run searches without forcing the relational database to become a high-volume trace store.

### G. Grafana

Grafana provides operational dashboards and trace exploration.

The MVP should include:

* Agent overview.
* Run volume and success/failure rates.
* Latency percentiles.
* LLM and tool-call performance.
* Token usage trends.
* Ingestion health.
* Links from metric panels to relevant traces or run history.

Alerting can use Grafana alerting or a compatible alerting component.

### H. AgentOps MCP Server

The MCP server exposes read-only observability tools to compatible clients.

Responsibilities:

* Register and expose MCP tools.
* Validate and authorize requests.
* Query the metrics, trace, and run-history backends through a service layer.
* Return structured, bounded responses.
* Enforce tenant and agent-level access restrictions.
* Provide consistent error handling and timeouts.

The MCP server should not directly expose unrestricted database access to clients.

### I. AI Diagnostic Assistant

The diagnostic assistant is a dedicated AI-powered interface that uses AgentOps MCP tools to investigate observability questions.

It should:

1. Understand a user's diagnostic question.
2. Select relevant read-only tools.
3. Query metrics, run records, and traces.
4. Correlate returned evidence.
5. Explain the likely cause or contributing factors.
6. Cite the relevant run IDs, trace IDs, timestamps, or metric observations.
7. Identify missing evidence and uncertainty.
8. Recommend next investigative steps.

The assistant is a consumer of the observability layer, not the system of record.

Its LLM provider, hosting model, UI, and conversation persistence strategy remain open decisions.

---

# 7. Functional Requirements

Priority definitions:

* **P0:** Required for the MVP.
* **P1:** Important follow-up capability.
* **P2:** Later enhancement.

## FR-01: Agent Instrumentation

**Priority: P0**

The system shall support telemetry collection through a native SDK and at least one wrapper/adapter integration path.

Acceptance criteria:

* A developer can instrument a sample agent using documented steps.
* Both integration paths emit the same canonical event and trace model.
* Telemetry identifies the agent and environment.
* Instrumentation failures do not unnecessarily crash the agent.
* Sensitive fields can be excluded or redacted before transmission.

## FR-02: Standardized Telemetry Schema

**Priority: P0**

The system shall define a versioned schema for agent execution, LLM operations, tool operations, and errors.

Required conceptual event types include:

* `run_started`
* `run_completed`
* `run_failed`
* `llm_call_started`
* `llm_call_completed`
* `tool_call_started`
* `tool_call_completed`
* `tool_call_failed`

The exact implementation may represent lifecycle operations as trace spans, events, or both.

Common fields should include:

* `schema_version`
* `event_id`
* `agent_id`
* `run_id`
* `environment`
* `timestamp`
* `event_type`
* `status`
* `duration`
* `trace_id`
* `span_id`
* `parent_span_id`, when applicable
* `deployment_version`, when available
* `error_type`, when applicable

LLM operations may additionally include model name, provider, token usage, and request status where available.

Acceptance criteria:

* Events and spans are validated against a versioned schema.
* Missing optional fields do not invalidate otherwise valid telemetry.
* SDK and adapter output can be correlated through common IDs.
* Schema evolution does not silently reinterpret older records.

## FR-03: Telemetry Ingestion

**Priority: P0**

The ingestion layer shall receive, validate, normalize, and route telemetry.

Acceptance criteria:

* Authenticated clients can submit valid telemetry.
* Invalid payloads return meaningful errors.
* Telemetry can be buffered or retried according to configurable limits.
* The collector exposes health and ingestion metrics.
* Repeated delivery does not create uncontrolled duplicate run records.

## FR-04: Operational Metrics

**Priority: P0**

The platform shall expose metrics covering agent execution and telemetry pipeline health.

Required metrics include:

* Run count by status.
* Success and failure rate.
* Run duration distribution.
* LLM-call duration.
* Tool-call duration.
* LLM and tool-call error counts.
* Token usage where provided by the integration.
* Telemetry ingestion success/failure.
* Collector queue or buffer health, where applicable.

Acceptance criteria:

* Metrics can be filtered by agent, environment, and time range.
* Latency percentiles can be calculated from appropriate histogram data.
* Metric labels avoid unbounded values such as raw prompts, user IDs, and run IDs.
* Metric definitions and units are documented.

## FR-05: Detailed Distributed Tracing

**Priority: P0**

The platform shall capture and query detailed traces for supported agent execution paths.

Acceptance criteria:

* A run can be associated with a trace ID.
* Child operations can be linked to their parent spans.
* LLM and tool-call spans include start time, duration, and status.
* Errors can be associated with the relevant span.
* Trace data can be filtered or retrieved by supported IDs and time ranges.
* The system identifies incomplete or partially sampled traces where possible.
* Sensitive span attributes are redacted according to configuration.

## FR-06: Run History

**Priority: P0**

The platform shall provide searchable historical records of individual agent runs.

Required capabilities:

* Search by agent and environment.
* Filter by status and time range.
* Filter by error category when available.
* View run duration and summarized operation counts.
* Retrieve the associated trace.
* Inspect sanitized error summaries.
* Paginate results and enforce maximum query ranges.

Acceptance criteria:

* A failed run can be found and opened without searching raw application logs manually.
* The run record links to its trace when trace data is available.
* Missing or expired trace data is indicated clearly.
* Run history retention is configurable.

## FR-07: Grafana Dashboards

**Priority: P0**

The system shall provide dashboards for operational monitoring.

Acceptance criteria:

* An overview dashboard shows run volume, error rate, and latency.
* Users can filter dashboards by agent, environment, and time range.
* Users can inspect LLM and tool-call performance.
* Dashboards expose ingestion health.
* Relevant run or trace exploration paths are available.

## FR-08: MCP Monitoring Tools

**Priority: P0**

The MCP server shall expose read-only tools for querying observability data.

Initial tool set:

| Tool                 | Purpose                                       |
| -------------------- | --------------------------------------------- |
| `list_agents`        | List agents accessible to the caller          |
| `get_agent_health`   | Return health indicators for an agent         |
| `get_agent_metrics`  | Query selected metrics over a time range      |
| `get_agent_latency`  | Retrieve latency summaries and distributions  |
| `get_agent_failures` | Summarize failures over a time range          |
| `search_runs`        | Search run history using supported filters    |
| `get_run_details`    | Retrieve a specific run summary               |
| `get_run_trace`      | Retrieve a bounded trace summary              |
| `get_trace_details`  | Retrieve span details for a trace             |
| `get_llm_usage`      | Summarize token usage and model-call activity |

Acceptance criteria:

* Tools have documented inputs, outputs, and error responses.
* Requests enforce authentication and authorization.
* Time ranges, result counts, and payload sizes are bounded.
* Tools return structured data suitable for an AI client.
* A tool cannot access an agent or tenant outside the caller's permissions.
* Tool descriptions make clear whether results are summaries or full records.

## FR-09: AI Diagnostic Assistant

**Priority: P0**

The platform shall provide a dedicated AI assistant that investigates agent behavior using authorized observability tools.

Required MVP scenarios:

1. Explain why a specific run failed.
2. Investigate unusually slow runs.
3. Summarize recurring failure patterns.
4. Compare successful and failed runs within a defined time window.
5. Identify expensive or high-latency LLM/tool operations.
6. Explain changes in error rate or latency using available metrics and traces.

Acceptance criteria:

* The assistant can invoke authorized AgentOps MCP tools.
* Findings include supporting run IDs, trace IDs, timestamps, or metric observations.
* The assistant distinguishes observed facts from inferred causes.
* It reports when evidence is incomplete or unavailable.
* It does not claim certainty when the telemetry only supports a hypothesis.
* It cannot execute production remediation actions in the MVP.
* Tool outputs are treated as data, not trusted instructions.

## FR-10: Security and Access Control

**Priority: P0**

The system shall authenticate telemetry producers and authorize monitoring users and clients.

Acceptance criteria:

* Credentials are not embedded in source code or telemetry payloads.
* Access is restricted to authorized agents, environments, and tenants.
* Secrets and sensitive payload fields can be redacted.
* MCP tools enforce access checks on every request.
* Diagnostic queries follow the same authorization boundaries as direct queries.
* Access-sensitive operations produce audit records where configured.

## FR-11: Agent Registration and Discovery

**Priority: P1**

The platform should provide a mechanism to register agents and their metadata.

Potential fields include agent name, environment, owner, deployment version, framework, and integration type.

For the MVP, registration may be configuration-driven or created automatically from authenticated telemetry. The final mechanism remains undecided.

## FR-12: Alerting

**Priority: P1**

The platform should support alerts for configurable operational conditions.

Examples include:

* Elevated failure rate.
* Latency above a configured threshold.
* No telemetry received from an expected agent.
* Increased LLM or tool-call errors.
* Collector or storage degradation.

## FR-13: Extended Historical Analytics

**Priority: P2**

The platform may add deeper cross-agent comparisons, advanced anomaly detection, and long-term trend analysis after the core metrics, traces, and run-history capabilities are stable.

---

# 8. Non-Functional Requirements

## NFR-01: Reliability

Telemetry collection should fail gracefully. A temporary observability outage should not automatically cause an otherwise healthy agent run to fail.

## NFR-02: Performance

Instrumentation overhead should be measured against an uninstrumented baseline. The MVP should establish explicit latency and throughput budgets through load testing rather than assuming one universal target.

## NFR-03: Scalability

The ingestion and storage layers should support horizontal scaling where needed. Buffer limits, backpressure, and sampling policies must be configurable.

## NFR-04: Security

* Encrypt network traffic in transit.
* Store credentials securely.
* Apply least-privilege access.
* Redact configured sensitive data before export.
* Protect the diagnostic assistant against prompt injection through telemetry content.
* Avoid storing raw prompts and responses by default unless explicitly configured.

## NFR-05: Data Isolation

If multi-tenancy is supported, tenant isolation must be enforced across ingestion, metrics queries, trace retrieval, run history, and MCP tools. A tenant identifier alone is not a sufficient authorization mechanism.

## NFR-06: Maintainability

SDKs, adapters, ingestion, query services, MCP tools, and the diagnostic assistant should have clearly defined interfaces and independently testable responsibilities.

## NFR-07: Observability of AgentOps Itself

AgentOps should monitor its own ingestion failures, query latency, storage errors, dropped telemetry, assistant tool failures, and resource consumption.

## NFR-08: Retention

Metrics, traces, and run metadata may require different retention periods. Each storage layer should support configurable retention and documented expiration behavior.

## NFR-09: Diagnostic Transparency

AI-generated explanations must link claims to available evidence and identify uncertainty. The assistant must not present correlation as proof of causation.

---

# 9. Data Model

The following is a proposed logical model, not a final database schema.

## 9.1 Agent

* `agent_id`
* `name`
* `environment`
* `framework`
* `integration_type`
* `deployment_version`
* `created_at`
* `metadata`

## 9.2 Run

* `run_id`
* `agent_id`
* `environment`
* `trace_id`
* `start_time`
* `end_time`
* `duration_ms`
* `status`
* `error_type`
* `error_summary`
* `deployment_version`
* `llm_call_count`
* `tool_call_count`
* `token_usage_summary`
* `metadata`

## 9.3 Trace Span

* `trace_id`
* `span_id`
* `parent_span_id`
* `run_id`
* `operation_name`
* `operation_type`
* `start_time`
* `end_time`
* `duration_ms`
* `status`
* `error_type`
* `attributes`

## 9.4 Metric

Metrics should follow Prometheus conventions, with documented names, types, units, and labels. Individual run IDs should generally not be metric labels because they can create excessive cardinality.

## 9.5 Data Relationship

A run is the user-facing execution record. A trace provides the detailed execution timeline. Metrics aggregate behavior across many runs.

A run may have a trace even when some spans are missing, and historical run metadata may remain available after its detailed trace expires.

---

# 10. Proposed API and MCP Interface

## 10.1 Ingestion and Health Endpoints

Proposed HTTP endpoints:

* `POST /v1/telemetry/events` — accept normalized telemetry events, if a custom ingestion API is used.
* `POST /v1/telemetry/traces` — accept trace payloads, if the implementation does not use a standard OTLP receiver directly.
* `GET /metrics` — expose Prometheus scrape metrics.
* `GET /health/live` — report process liveness.
* `GET /health/ready` — report readiness to accept work.

**Implementation decision:** prefer OpenTelemetry Protocol (OTLP) for trace ingestion where practical. A custom event endpoint may still be needed for run metadata or a simplified SDK experience. Avoid maintaining two overlapping trace-ingestion formats without a clear need.

## 10.2 Query Service

The query/service layer should provide internal interfaces for:

* Metric queries.
* Run-history searches.
* Run-detail retrieval.
* Trace searches and retrieval.
* Agent discovery.
* Authorization and tenant scoping.

The MCP server and diagnostic assistant should use these interfaces rather than independently implementing storage queries.

## 10.3 MCP Tool Contracts

Every tool should define:

* Input schema.
* Output schema.
* Authorization requirements.
* Time-range and result-size limits.
* Timeout behavior.
* Error format.
* Whether its output is a summary or detailed record.

Large traces should be returned through bounded summaries and pagination or follow-up queries rather than unrestricted payloads.

---

# 11. Proposed Technology Stack

| Layer                | Initial proposal                             | Rationale                                          |
| -------------------- | -------------------------------------------- | -------------------------------------------------- |
| SDK                  | Python                                       | Initial developer integration                      |
| Wrapper/adapters     | Python integrations                          | Reuse SDK and schema                               |
| API/collector        | FastAPI and/or OpenTelemetry Collector       | Custom ingestion plus standard telemetry transport |
| Metrics              | Prometheus                                   | Time-series metrics                                |
| Tracing              | OpenTelemetry + Grafana Tempo                | Distributed trace collection and storage           |
| Run history          | PostgreSQL                                   | Searchable execution metadata                      |
| Dashboards           | Grafana                                      | Metrics and trace exploration                      |
| MCP server           | Python MCP SDK                               | Expose structured monitoring tools                 |
| Diagnostic assistant | LLM provider behind a configurable interface | Evidence-based investigation                       |
| Deployment           | Docker Compose for local MVP                 | Reproducible development environment               |
| Testing              | pytest plus integration/load tests           | Validate components and end-to-end behavior        |

This stack is a working proposal. The product requirements should remain portable enough to accommodate alternative backends later.

---

# 12. MVP Scope and Definition of Done

The MVP is complete when all of the following are demonstrated end to end:

1. A sample AI agent can be instrumented using the SDK.
2. A supported wrapper/adapter can instrument an existing agent.
3. Both integrations produce consistent run metadata and correlated traces.
4. Prometheus collects the required operational metrics.
5. Grafana displays agent health, latency, failures, and usage metrics.
6. Individual runs are searchable in the run-history interface or API.
7. Run records link to their associated traces.
8. MCP clients can query metrics, run history, and trace summaries.
9. The dedicated diagnostic assistant can investigate a failed or slow run using MCP tools.
10. Diagnostic explanations include evidence and communicate uncertainty.
11. Authentication, authorization, redaction, and retention behavior are documented and tested.
12. A local deployment can be started using documented instructions.
13. Automated tests cover the primary integration and investigation workflows.

**MVP exclusion:** autonomous remediation, unrestricted agent control, and automatic production changes.

---

# 13. Testing Strategy

## Unit Tests

* SDK event generation.
* Adapter normalization.
* Schema validation.
* Redaction rules.
* Query-service filters.
* MCP input validation and authorization.
* Diagnostic response evidence formatting.

## Integration Tests

* SDK to ingestion to storage.
* Adapter to ingestion to storage.
* Run metadata to trace correlation.
* Prometheus metric collection.
* Run-history searches.
* MCP tool calls against test data.
* Diagnostic assistant investigations using controlled fixtures.

## End-to-End Tests

Simulate an agent that:

1. Starts a run.
2. Makes an LLM call.
3. Calls a tool.
4. Encounters a failure.
5. Emits the corresponding telemetry.
6. Appears in dashboards and run history.
7. Can be investigated through an MCP client and the diagnostic assistant.

## Security Tests

* Unauthorized agent access.
* Cross-tenant query attempts, if multi-tenancy is enabled.
* Sensitive-data redaction.
* Prompt injection embedded in trace attributes or error messages.
* Excessive time ranges and oversized responses.
* Credential leakage in logs.

## Performance Tests

Measure:

* Instrumentation overhead.
* Ingestion throughput.
* Telemetry loss under load.
* Trace and run-history query latency.
* Metric query latency.
* Assistant investigation latency and tool-call count.

Concrete service-level objectives should be defined after initial workload assumptions are agreed upon.

---

# 14. Risks and Mitigations

| Risk                                                     | Mitigation                                                           |
| -------------------------------------------------------- | -------------------------------------------------------------------- |
| Framework diversity makes instrumentation inconsistent   | Canonical schema plus framework-specific adapters                    |
| Instrumentation increases application latency            | Asynchronous export, bounded buffering, configurable sampling        |
| High-cardinality metrics overload Prometheus             | Keep run IDs and other unique identifiers out of metric labels       |
| Trace volume increases storage costs                     | Configurable sampling, retention, and trace limits                   |
| Sensitive information enters telemetry                   | Default-deny payload capture, redaction, explicit opt-in for content |
| AI assistant invents a root cause                        | Require evidence references and explicit uncertainty                 |
| Trace and run records become inconsistent                | Shared IDs, lifecycle rules, idempotent processing, reconciliation   |
| MCP tools expose excessive data                          | Authorization, bounded responses, pagination, query limits           |
| Diagnostic assistant becomes coupled to one LLM provider | Provider abstraction and configurable model integration              |
| Observability failure disrupts the agent                 | Fail-open instrumentation behavior and bounded export queues         |

---

# 15. Remaining Assumptions and Open Decisions

The following items have **not** been settled by the current product decisions. They should be confirmed before implementation is finalized.

## A. Initial Framework and Language Support

**Working assumption:** Python is the first-class SDK language, with at least one supported Python agent-framework adapter.

Open decision: Which specific agent framework or framework-neutral integration should be the first supported path?

Why it matters: This determines callback APIs, trace propagation, SDK design, and acceptance-test coverage.

## B. Wrapper Coverage

**Working assumption:** SDK and wrappers/adapters are both MVP capabilities, but the MVP will support a limited set of integrations.

Open decision: Which wrappers are mandatory, and must integrations work with unmodified third-party agent code?

Why it matters: A generic wrapper cannot reliably observe internal LLM and tool operations unless the framework exposes suitable hooks.

## C. Deployment Model

**Working assumption:** Docker Compose provides the initial local deployment.

Open decision: Is the target deployment self-hosted, cloud-hosted SaaS, customer-managed infrastructure, or a combination?

Why it matters: Deployment affects identity management, tenant isolation, upgrades, data residency, and operational ownership.

## D. Tenant Model and Authentication

**Working assumption:** Authentication and authorization are required; a production multi-tenant design must be supported if multiple customer organizations share an installation.

Open decision: Is the MVP single-tenant, multi-tenant, or both? Which identity provider and authentication mechanisms are required?

Why it matters: Tenant boundaries must be designed into ingestion and querying rather than added after data is stored.

## E. Diagnostic Assistant Interface

**Working assumption:** The assistant uses AgentOps MCP tools and is separate from the monitored agent's runtime.

Open decision: Should the assistant be a web UI, CLI, API, embedded interface, or multiple interfaces? Which LLM provider or model-hosting approach should be used?

Why it matters: This determines user experience, conversation handling, model credentials, and privacy requirements.

## F. Telemetry Content and Privacy

**Working assumption:** The platform captures operational metadata and does not collect raw prompts, model responses, or sensitive payloads by default.

Open decision: Should optional prompt/response capture be supported, and what redaction, consent, encryption, and retention controls are required?

Why it matters: Full content can help debugging but materially increases privacy, security, and storage risks.

## G. Trace and Run Retention

**Working assumption:** Metrics, traces, and run metadata have separate retention policies.

Open decision: What retention periods, sampling defaults, and maximum trace sizes should apply?

Why it matters: These choices determine infrastructure cost, historical search capabilities, and the diagnostic assistant's available evidence.

## H. Scale and Service Objectives

**Working assumption:** The MVP is initially designed for a limited number of agents and a measurable test workload, with a path to horizontal scaling.

Open decision: What are the expected agents, runs per second, span volume, retention volume, and acceptable query latency?

Why it matters: Without a workload profile, precise capacity planning and performance targets would be speculative.

## I. Alerts and Notifications

**Working assumption:** Dashboards are P0 and advanced alerting is P1.

Open decision: Must the MVP send notifications to Slack, email, PagerDuty, or another system, or is dashboard-based monitoring sufficient initially?

## J. Registration and Discovery

**Working assumption:** Initial agent registration can be configuration-driven or inferred from authenticated telemetry.

Open decision: Is a management UI and explicit registration workflow required for the MVP?

## K. Assistant Permissions and Auditability

**Working assumption:** The assistant is read-only and operates under the requesting user's permissions.

Open decision: Must every tool call and diagnostic query be auditable, and what audit retention or approval requirements apply?

## L. Success Criteria

**Working assumption:** The MVP is evaluated through successful instrumentation, telemetry correlation, trace/run retrieval, and evidence-backed diagnostic workflows.

Open decision: What quantitative targets define success for onboarding time, telemetry overhead, data completeness, diagnostic latency, and investigation usefulness?

---

# 16. Recommended Delivery Milestones

## Milestone 1 — Telemetry Foundation

* Finalize the canonical schema.
* Build the initial SDK.
* Implement the first adapter.
* Implement ingestion and health endpoints.
* Establish run and trace correlation.

## Milestone 2 — Observability Storage

* Configure Prometheus.
* Configure the trace backend.
* Implement run-history persistence.
* Add retention and redaction behavior.
* Verify end-to-end telemetry ingestion.

## Milestone 3 — Monitoring and Investigation APIs

* Build Grafana dashboards.
* Implement the query/service layer.
* Add MCP monitoring tools.
* Enforce authentication and access control.
* Test run-history and trace retrieval.

## Milestone 4 — AI Diagnostic Assistant

* Connect the assistant to authorized MCP tools.
* Implement evidence-backed failure investigation.
* Add slow-run and recurring-failure workflows.
* Test incomplete evidence, incorrect hypotheses, and prompt injection.
* Ensure that the assistant cannot execute production changes.

## Milestone 5 — MVP Hardening

* Run integration, security, and load tests.
* Establish baseline performance and reliability targets.
* Document deployment, onboarding, troubleshooting, and retention.
* Validate the complete user journey with a representative agent.

---

# 17. Final Product Definition

AgentOps MCP is a **framework-extensible observability and diagnostic platform for AI agents**.

Its core capabilities are:

1. **Instrument:** use an SDK or wrapper/adapter.
2. **Collect:** normalize and ingest agent telemetry.
3. **Observe:** monitor aggregate metrics through Prometheus and Grafana.
4. **Trace:** inspect detailed execution paths and individual operations.
5. **Search:** retrieve historical runs and correlate them with traces.
6. **Query:** expose authorized monitoring operations through MCP.
7. **Diagnose:** use a dedicated AI assistant to investigate operational questions using evidence from metrics, traces, and run history.

The key architectural principle is that the **SDK and adapters generate telemetry; the observability backends store it; the MCP server exposes it; and the diagnostic assistant interprets it**. Keeping these responsibilities separate will make the system easier to extend, test, secure, and operate.
