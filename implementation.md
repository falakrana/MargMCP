# AgentOps MCP --- Phase-Wise Implementation Instructions

**Document type:** Implementation playbook and coding-agent operating
instructions\
**Intended users:** Cursor, Claude Code, OpenCode, or another
repository-aware coding agent\
**Project:** AgentOps MCP\
**Primary rule:** Implement exactly one phase at a time. The human owner
verifies every phase and explicitly authorizes the next phase.

------------------------------------------------------------------------

## 0. Operating Contract --- Read This First

You are the senior engineer responsible for implementing AgentOps MCP in
the repository where this file is placed. Work as a careful,
production-minded engineer. Do not treat this document as permission to
implement the entire project in one run.

### 0.1 Mandatory phase gate

1.  Start by inspecting the repository, existing code, project
    instructions, and all relevant PRD/SRS/design documents. Do not
    overwrite or replace existing work before understanding it.
2.  Determine the current implementation phase from the repository and
    `IMPLEMENTATION_STATUS.md` if it exists. If no status file exists,
    create one during Phase 1.
3.  If the repository is empty, begin Phase 1. If work already exists,
    map it to the phase gates and report the current state before
    changing anything.
4.  Implement **only the current phase**. Do not begin tasks from the
    next phase, even if they seem easy or related.
5.  At the end of the phase:
    -   run the relevant automated tests, linting, type checks,
        formatting checks, and build commands available in the
        repository;
    -   fix issues caused by your changes;
    -   update documentation and `IMPLEMENTATION_STATUS.md`;
    -   provide a concise implementation report, changed-file list, test
        results, known limitations, and a human verification checklist;
    -   stop and wait for the human owner to verify the phase.
6.  Do not continue until the human explicitly responds with an approval
    such as **`APPROVE PHASE 1`**. An ambiguous message is not approval.
    If the owner requests changes, remain in the same phase and address
    only those changes.
7.  After approval, begin the next phase only when asked to continue or
    when the approval clearly authorizes moving forward. Never silently
    chain phases.
8.  Do not claim a test passed unless you actually ran it and observed
    its result. If a command cannot run because of missing dependencies,
    unavailable services, or environment constraints, report it as
    blocked and explain why.
9.  Never fabricate integrations, metrics, trace data, API responses, or
    successful deployment results. Clearly label demo/seed data as demo
    data.
10. Ask a focused question before proceeding only when a blocking
    decision cannot safely be resolved from the repository or this
    document. Otherwise use the stated defaults, record assumptions, and
    keep moving within the current phase.

### 0.2 Required status file

Maintain `IMPLEMENTATION_STATUS.md` at the repository root with: -
current phase and status (`NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`,
`READY_FOR_REVIEW`, `APPROVED`); - completed tasks and acceptance
criteria; - commands executed and their actual results; - known issues
and deferred decisions; - human verification steps; - the next phase,
which must remain unstarted until approval.

Do not mark a phase `APPROVED` yourself. Only the human owner can
approve it. You may mark it `READY_FOR_REVIEW`.

### 0.3 Safety and engineering rules

-   Preserve existing user changes. Do not reset, clean, or overwrite
    unrelated work.
-   Never print, commit, or expose API keys, credentials, `.env` values,
    tokens, customer prompts, or private production payloads.
-   Do not introduce destructive database migrations, data deletion,
    cloud resources, paid services, or production deployment actions
    without explicit human approval.
-   Use environment variables and a committed `.env.example`; never
    commit a real `.env`.
-   Keep telemetry collection non-blocking and bounded. A telemetry
    outage must not normally break the monitored agent.
-   Avoid high-cardinality Prometheus labels. Do not use `run_id`, user
    IDs, raw prompts, or arbitrary error messages as metric labels.
-   Do not capture full prompts, outputs, secrets, or personal data by
    default. Make sensitive payload capture opt-in and support
    redaction.
-   Use pinned or bounded dependency versions and update lockfiles when
    applicable.
-   Follow existing project conventions when they are sound. Do not
    introduce a second framework or duplicate infrastructure without a
    documented reason.
-   Do not implement a feature as a fake or stub and present it as
    production-ready. If a stub is temporarily necessary, label it
    clearly and add a test or issue describing the gap.
-   Keep changes focused. Avoid unrelated refactors.

------------------------------------------------------------------------

## 1. Product Goal and Scope

AgentOps MCP is an observability platform for deployed AI agents. It
combines:

1.  **An SDK plus wrappers/adapters** that developers integrate into
    their agents.
2.  **A telemetry ingestion and query backend** that receives,
    validates, stores, and serves execution data.
3.  **Metrics, detailed traces, and run history** as the MVP
    observability scope.
4.  **An observability dashboard** for human operators.
5.  **An MCP server** that exposes safe, structured monitoring tools to
    compatible MCP clients.
6.  **A dedicated AI diagnostic assistant** that uses retrieved
    telemetry to explain failures and performance issues with evidence
    and uncertainty.

The SDK is not a separate product plugin that must be rewritten for
every agent. The core SDK and event schema should remain stable;
framework-specific wrappers/adapters translate framework lifecycle
events into the common AgentOps schema.

### 1.1 MVP user journey

A developer should be able to:

1.  Create/register a project and agent.
2.  Install and configure the AgentOps SDK.
3.  Add the SDK or a supported adapter to an existing Python agent.
4.  Run the agent without major changes to its business logic.
5.  See run status, duration, errors, metrics, traces, and run history
    in the dashboard.
6.  Connect an MCP-compatible client and query the same data through
    AgentOps MCP tools.
7.  Ask the diagnostic assistant why a run failed or became slower and
    receive an evidence-backed explanation.
8.  Control access, payload capture, redaction, and retention.

### 1.2 Explicitly out of initial scope

Unless the existing PRD specifically requires otherwise, do not add
these to the MVP: - autonomous remediation or making production
changes; - automatic agent code modification; - unrestricted remote
execution of tools; - a marketplace of integrations; - billing and
complex multi-plan monetization; - support for every agent framework
from day one; - advanced evaluation, prompt optimization, or model
training; - multi-region high availability before core behavior is
validated.

The diagnostic assistant is **read-only** in the MVP. It may recommend
checks but must not modify production agents, infrastructure, prompts,
or data.

------------------------------------------------------------------------

## 2. Architecture and Defaults

First inspect the repository and project documents. Existing approved
decisions take precedence over the defaults below. If there is a
conflict, record it and ask the owner only if it materially blocks
implementation.

### 2.1 Proposed logical architecture

``` text
Monitored Python Agent
    |
    +-- AgentOps SDK / Framework Adapter
            |
            +-- Run lifecycle + events + trace/span context
            +-- Bounded buffering / batching / retry
            +-- Redaction and sampling
            |
            v
      Authenticated Ingestion API (FastAPI)
            |
            +-- Validate and normalize telemetry
            +-- Persist run metadata/events
            +-- Export metrics
            +-- Export traces
            |
            +--> Primary application database
            +--> Prometheus metrics
            +--> OpenTelemetry-compatible trace pipeline / Tempo
                         |
                         v
                  Dashboard APIs
                         |
              React + TypeScript Dashboard

MCP Client --> AgentOps MCP Server --> Authorized AgentOps Query Services
                                          |
                                          +--> Metrics
                                          +--> Runs / events
                                          +--> Traces
                                          +--> Error summaries
                                                   |
                                                   v
                                      AI Diagnostic Assistant
                                      (read-only, evidence-based)
```

### 2.2 Recommended starting stack

Use the repository's existing stack if already established. Otherwise
use these defaults and document any deviation:

-   **SDK and backend:** Python, type hints, `pyproject.toml`, FastAPI,
    Pydantic.
-   **Instrumentation and context propagation:** OpenTelemetry APIs/SDK
    where useful.
-   **MCP server:** Python MCP SDK or the maintained MCP implementation
    already selected in the repository.
-   **Dashboard:** React + TypeScript; use the existing build tool and
    UI conventions if present.
-   **Metrics:** Prometheus.
-   **Metrics dashboards:** Grafana for operational/internal dashboards;
    the product UI may also show key metrics.
-   **Trace storage:** OpenTelemetry-compatible trace pipeline, with
    Grafana Tempo as the initial candidate if no choice is already made.
-   **Application metadata/run persistence:** Choose one primary
    database. Default to MongoDB if no repository or PRD decision
    exists; PostgreSQL is also acceptable if existing infrastructure
    favors relational querying.
-   **Local development:** Docker Compose for dependencies where
    appropriate.
-   **Testing:** pytest for Python; the existing JavaScript/TypeScript
    test runner for the dashboard.
-   **Code quality:** Ruff (or existing Python linter/formatter), static
    typing where practical, ESLint, and TypeScript checks.

Do not store every trace span in Prometheus. Prometheus is for numeric
time-series metrics; traces belong in a trace backend or appropriate
event storage. Grafana can visualize multiple observability data
sources.

### 2.3 Keep storage responsibilities explicit

-   **Primary database:** project/agent configuration, run metadata,
    event records needed for history and query APIs, and ingestion
    idempotency records if needed.
-   **Prometheus:** aggregate numeric time-series metrics.
-   **Trace backend:** detailed spans and parent/child trace
    relationships.
-   **Grafana:** visualization and alert/dashboard configuration; it is
    not the application's primary database.
-   **Secrets manager/environment:** API keys and credentials; never
    store plaintext secrets in ordinary run records.

Do not add Redis, Kafka, Celery, or another queue by default. Introduce
a queue only if measured ingestion requirements or an agreed
architecture require one.

------------------------------------------------------------------------

## 3. Cross-Phase Domain Contracts

Define and document these contracts early. Refine them when repository
evidence requires it, but avoid inconsistent identifiers or incompatible
payload shapes between components.

### 3.1 Core entities

-   **Organization/Tenant:** ownership and access boundary, even if the
    first local demo has only one tenant.
-   **Project:** logical workspace containing agents.
-   **Agent:** a deployed AI application or agent configuration.
-   **Run:** one top-level invocation of an agent.
-   **Trace:** a correlated execution path, potentially covering one or
    more operations.
-   **Span:** one timed operation within a trace; spans form
    parent/child relationships.
-   **Event:** a timestamped occurrence such as run started, tool
    called, retry, exception, or run completed.
-   **Metric:** a numeric measurement aggregated over time.
-   **Diagnostic report:** an assistant-generated hypothesis linked to
    supporting telemetry.

Use opaque, stable IDs. Do not use display names as identifiers.

### 3.2 Minimum run fields

At minimum, plan for: - `run_id`, `project_id`, `agent_id`, and
`tenant_id` where applicable; - `trace_id` and root `span_id` when
tracing is enabled; - `status` such as `running`, `success`, `error`,
`cancelled`, or `unknown`; - `started_at`, `ended_at`, and computed
duration; - SDK and schema version; - environment/deployment identifier
where configured; - safe metadata/tags with documented limits; - error
type/code and redacted error summary when applicable; - optional
token/cost fields only when actually available from the provider or
adapter; - references to trace data and events.

Use UTC timestamps internally and ISO-8601 timestamps in API responses.
Validate duration and status transitions.

### 3.3 Minimum trace/span fields

-   `trace_id`, `span_id`, optional `parent_span_id`;
-   operation name and operation type (`agent`, `llm`, `tool`,
    `retrieval`, `http`, or `custom`);
-   start/end timestamps and duration;
-   status and structured error details;
-   safe attributes such as provider/model, tool name, token counts, and
    retry count when available;
-   links to the corresponding project, agent, and run;
-   redacted input/output summaries only when capture is explicitly
    configured.

Never assume all frameworks expose all fields. Missing provider usage or
tool metadata must be represented as unavailable, not fabricated or
silently set to zero.

### 3.4 Metrics contract

Begin with: - total runs; - successful and failed runs; - run duration
histogram; - ingestion request count and latency; - telemetry
dropped/retry/error counts; - LLM/tool operation count and duration
where instrumentation provides them; - token usage and estimated cost
only when trustworthy source data is available.

Use bounded label sets such as environment, operation type, status,
provider, and model where appropriate. Never put IDs, prompts, arbitrary
user input, or exception messages into Prometheus labels.

### 3.5 API conventions

-   Version public APIs and telemetry schemas.
-   Validate all input and query parameters.
-   Use consistent pagination and sorting.
-   Return predictable structured error responses.
-   Apply limits to page size, payload size, query windows, and batch
    sizes.
-   Enforce authorization in backend services, not only in the UI.
-   Document endpoints and MCP tools.
-   Keep ingestion payloads backward-compatible where feasible; reject
    unsupported schema versions clearly.

------------------------------------------------------------------------

## 4. Phase 1 --- Repository Discovery, Architecture, and Implementation Plan

**Objective:** Understand the existing codebase and convert the
requirements into an implementation-ready baseline without building
later-phase features.

### Tasks

1.  Inspect:
    -   root files and directory structure;
    -   README, PRD/SRS, architecture notes, `AGENTS.md`, `CLAUDE.md`,
        Cursor rules, and other repository instructions;
    -   existing package manifests, lockfiles, tests, CI, Docker files,
        environment examples, and deployment configuration;
    -   current Git status and uncommitted changes.
2.  Summarize what already exists. Do not recreate existing components.
3.  Identify gaps against this implementation plan.
4.  Propose a modular directory structure suited to the current
    repository. Do not force a monorepo or restructure a functioning
    project without reason.
5.  Document architecture, component boundaries, request/data flow,
    trust boundaries, and storage responsibilities.
6.  Define the first version of telemetry schemas and API/MCP contract
    boundaries.
7.  Record assumptions and unresolved decisions in
    `docs/assumptions-and-decisions.md`.
8.  Create or update:
    -   `IMPLEMENTATION_STATUS.md`;
    -   `docs/architecture.md`;
    -   `docs/telemetry-schema.md`;
    -   `docs/implementation-plan.md` or an equivalent phase checklist.
9.  Add an initial testing strategy, including unit, integration,
    contract, security, and manual verification tests.

### Do not do in Phase 1

-   Do not implement the SDK, ingestion API, dashboard, MCP tools, or
    assistant.
-   Do not install a large set of dependencies without need.
-   Do not provision cloud infrastructure or modify production systems.
-   Do not choose a database/trace backend contrary to an existing
    decision.

### Acceptance criteria

-   The current repository state and existing functionality are
    documented.
-   The proposed architecture matches the product scope.
-   Data flow and component responsibilities are understandable.
-   Assumptions and unresolved decisions are visible.
-   The phase plan has testable exit criteria.
-   No unrelated application behavior has changed.

### Human verification checklist

-   Is the architecture correct?
-   Are the initial stack and storage choices acceptable?
-   Are the entity IDs and telemetry fields sufficient?
-   Is the proposed repository structure reasonable?
-   Are assumptions correctly distinguished from fixed requirements?

**Stop after Phase 1 and wait for explicit approval.**

------------------------------------------------------------------------

## 5. Phase 2 --- Core SDK and First Instrumentation Adapter

**Objective:** Instrument one Python agent and emit consistent run
lifecycle telemetry with minimal changes to application logic.

### Tasks

1.  Establish the SDK package structure and public API.
2.  Provide configuration for API endpoint, API key, project/agent IDs,
    environment, timeouts, sampling, and privacy options.
3.  Implement run lifecycle operations:
    -   start a run;
    -   attach safe metadata/tags;
    -   record events;
    -   set output summary if permitted;
    -   finish successfully;
    -   record an error;
    -   handle cancellation and exceptions.
4.  Implement context management so a run is finalized even when the
    wrapped agent raises an exception.
5.  Create an abstraction for exporters so the SDK is not coupled to one
    backend transport.
6.  Implement bounded buffering/batching and configurable request
    timeouts. Keep retry behavior bounded and avoid unbounded memory
    growth.
7.  Add idempotency or stable event IDs so retries do not create
    duplicate logical events.
8.  Add redaction hooks and ensure payload capture is off by default.
9.  Propagate trace/run context through supported nested operations.
10. Implement the first generic Python wrapper/decorator or context
    manager. Keep the adapter contract extensible for future frameworks.
11. Add a small example agent and integration test.
12. Provide package usage documentation and `.env.example` without real
    secrets.

### Expected developer experience

The public API should be simple and documented. Illustrative shape only;
adapt it to repository conventions:

``` python
from agentops_mcp import AgentOps

agentops = AgentOps.from_env()

with agentops.start_run(agent_name="support-agent") as run:
    result = my_agent.invoke({"question": "Example question"})
    run.set_output_summary({"result_type": "answer"})
```

Do not blindly copy this exact API if it conflicts with the existing
design. Keep full prompts and outputs out of telemetry by default.

### Tests

-   successful run lifecycle;
-   exception/failure lifecycle;
-   cancellation/finalization behavior;
-   missing optional metadata;
-   exporter timeout and backend-unavailable behavior;
-   retry bounds and idempotency;
-   redaction and payload-capture defaults;
-   SDK disabled or misconfigured behavior;
-   nested context propagation;
-   no unhandled telemetry exception escapes into normal application
    logic under default best-effort mode.

### Acceptance criteria

-   A sample Python agent can be instrumented with a small integration
    change.
-   A run produces a valid normalized telemetry payload.
-   Failed runs are recorded without hiding the original application
    exception.
-   Telemetry failure is bounded and does not normally break the agent.
-   The SDK has tests and usage documentation.

### Human verification checklist

-   Review the SDK public API and configuration.
-   Run the sample agent.
-   Force a sample exception and confirm correct run status.
-   Disable or misconfigure the telemetry endpoint and confirm bounded
    graceful behavior.
-   Inspect logs to ensure secrets and payloads are not leaked.

**Stop after Phase 2 and wait for explicit approval.**

------------------------------------------------------------------------

## 6. Phase 3 --- Ingestion API, Persistence, and Query Services

**Objective:** Receive SDK telemetry securely, validate it, persist it,
and make it queryable.

### Tasks

1.  Implement FastAPI application structure using routers, service
    layer, schemas, repository/data-access layer, configuration, and
    dependency injection consistent with the project.
2.  Implement authentication for SDK ingestion. Use secure key
    hashing/storage if API keys are persisted; never log keys.
3.  Define project/agent registration or configuration flow required by
    the MVP. Do not build a complex billing or organization-management
    system unless already required.
4.  Implement ingestion endpoints for run lifecycle/events/spans, using
    the approved contract.
5.  Validate schema version, IDs, timestamps, payload size, allowed
    attributes, and status transitions.
6.  Implement persistence using the selected primary database.
7.  Ensure writes are idempotent where retries can occur.
8.  Add query services and endpoints for:
    -   list/filter runs;
    -   retrieve a run and its events;
    -   retrieve agent/project metadata;
    -   retrieve error summaries;
    -   pagination and time-range filters.
9.  Enforce project/tenant authorization at the service/query layer.
10. Add health/readiness endpoints without exposing secrets or internal
    sensitive details.
11. Add database indexes for actual query patterns, documented with the
    model.
12. Add database migration/index setup as appropriate for the selected
    database.
13. Add local development setup and seed/demo data clearly marked as
    synthetic.
14. Document API request/response examples and error codes.

### Tests

-   valid and invalid ingestion payloads;
-   missing/invalid authentication;
-   cross-project access denied;
-   duplicate event/run ingestion;
-   out-of-order events and lifecycle edge cases;
-   pagination, filtering, and time boundaries;
-   database failure and transaction/error behavior;
-   payload-size limits;
-   malformed timestamps and unsupported schema versions;
-   API contract tests.

### Acceptance criteria

-   An SDK payload can be received, validated, and persisted.
-   Persisted runs can be queried by project, agent, status, and time
    range.
-   Duplicate retries do not corrupt run history.
-   Unauthorized users cannot read or write another project's telemetry.
-   API documentation and automated tests are available.

### Human verification checklist

-   Start the backend and database locally.
-   Submit a valid run and retrieve it through the API.
-   Submit an invalid payload and inspect the structured error.
-   Try cross-project access with a different credential.
-   Restart services and confirm persisted records remain available.

**Stop after Phase 3 and wait for explicit approval.**

------------------------------------------------------------------------

## 7. Phase 4 --- Metrics, Prometheus, and Trace Export Pipeline

**Objective:** Turn telemetry into reliable metrics and detailed traces
using appropriate observability components.

### Tasks

1.  Instrument backend ingestion and processing with service metrics.
2.  Define application metrics for run counts, statuses, durations,
    LLM/tool operations where available, and ingestion health.
3.  Use bounded labels only. Review every label for cardinality and
    privacy risks.
4.  Expose or export Prometheus-compatible metrics with
    authentication/network boundaries appropriate to the environment.
5.  Configure Prometheus scrape targets and local development
    configuration.
6.  Add OpenTelemetry tracing for backend requests and SDK operations
    where applicable.
7.  Define span naming and attributes consistently; preserve trace/run
    correlation.
8.  Configure trace export and the selected trace backend (Tempo or the
    approved alternative).
9.  Configure trace retention and sampling defaults. Do not silently
    sample away error traces if the chosen policy intends to retain
    them.
10. Add Grafana provisioning/configuration for initial operational
    dashboards.
11. Keep telemetry pipelines isolated from business request failure
    paths.
12. Document local service startup, data flow, ports, and
    troubleshooting.

### Tests and validation

-   metric names/types and label bounds;
-   counters increment for the expected lifecycle events;
-   duration histogram observations are valid;
-   Prometheus can scrape the service;
-   a generated trace is exported and queryable in the trace backend;
-   trace/run identifiers correlate correctly;
-   exporter failure is observable but does not crash the application;
-   sensitive values are absent from labels and span attributes.

### Acceptance criteria

-   Metrics reflect actual test runs.
-   Prometheus scrapes the intended targets.
-   Detailed traces can be retrieved from the chosen backend.
-   Trace and run identifiers can be correlated.
-   A local developer can start the observability stack from documented
    commands.

### Human verification checklist

-   Open Prometheus targets and confirm expected targets are healthy.
-   Query run count and duration metrics.
-   Open a trace from a test run and inspect its spans.
-   Check that labels and attributes contain no prompt text, secrets, or
    unbounded IDs.
-   Stop the trace backend and confirm the agent/backend degrades
    safely.

**Stop after Phase 4 and wait for explicit approval.**

------------------------------------------------------------------------

## 8. Phase 5 --- Trace Details and Run History

**Objective:** Make a single run explainable from start to finish.

### Tasks

1.  Define the API contract that joins run metadata, events, and trace
    references without assuming all data is in one database.
2.  Implement trace retrieval by trace/run ID, including parent/child
    span ordering.
3.  Implement run-history filtering by time range, agent, status, and
    supported metadata.
4.  Implement event timeline ordering and handling of late/out-of-order
    events.
5.  Show duration and status for each span; distinguish errors, missing
    data, and incomplete traces.
6.  Add useful error summaries and safe stack/error metadata where
    permitted.
7.  Add optional input/output summaries only if explicitly enabled and
    redacted.
8.  Implement pagination and limits for large traces and histories.
9.  Add correlation links between a run, its trace, relevant metric time
    windows, and error records.
10. Document retention behavior when metadata remains but detailed
    traces expire, or vice versa.

### Tests

-   complete and incomplete traces;
-   missing parent spans;
-   late-arriving spans;
-   long traces and pagination;
-   run with no trace data;
-   trace backend timeout;
-   redacted and disabled payload capture;
-   time-zone display and UTC storage consistency;
-   correlation between run ID and trace ID.

### Acceptance criteria

-   A developer can find a run and inspect its timeline.
-   Nested spans are presented in the correct relationship.
-   Missing trace data is communicated accurately.
-   Large result sets are bounded and paginated.
-   Privacy settings are honored consistently.

### Human verification checklist

-   Inspect a successful run and a failed run.
-   Inspect a run with nested LLM/tool operations.
-   Inspect a run with incomplete trace data.
-   Verify time range filters and pagination.
-   Confirm sensitive inputs and outputs are not exposed by default.

**Stop after Phase 5 and wait for explicit approval.**

------------------------------------------------------------------------

## 9. Phase 6 --- Monitoring Dashboard

**Objective:** Provide a usable interface for registering agents and
inspecting metrics, runs, and traces.

### Tasks

1.  Inspect existing frontend conventions and reuse the current app if
    present.
2.  Implement authentication/session handling appropriate to the
    backend. Never put privileged service credentials in browser code.
3.  Build a responsive application shell and navigation.
4.  Implement screens:
    -   overview dashboard;
    -   projects/agents list and agent details;
    -   run history with filters and pagination;
    -   run detail and event timeline;
    -   trace/span explorer;
    -   errors/failure summary;
    -   settings for integration and privacy configuration as supported.
5.  Show loading, empty, stale-data, and error states. Never display
    mock metrics as if they are real.
6.  Add charts for run volume, success/failure, latency
    distributions/percentiles, and cost/token usage only when data is
    available.
7.  Link dashboard views to the actual query APIs.
8.  Provide clear status definitions and UTC/local-time handling.
9.  Ensure API errors are handled safely and do not expose stack traces
    or credentials.
10. Add accessibility basics, keyboard navigation, and responsive
    layouts.
11. Add frontend unit/component tests and end-to-end smoke tests if the
    repository supports them.

### Acceptance criteria

-   The dashboard uses live backend data.
-   Users can filter runs and open run/trace details.
-   Charts have correct units and empty states.
-   Errors and loading states are understandable.
-   UI authorization does not replace backend authorization.
-   Frontend lint/type/build/tests pass.

### Human verification checklist

-   Start the full local stack and sign in.
-   Compare dashboard values with API responses and Prometheus queries.
-   Filter runs by status and date.
-   Open a run and navigate to its trace.
-   Test empty data, backend unavailable, and narrow-screen behavior.

**Stop after Phase 6 and wait for explicit approval.**

------------------------------------------------------------------------

## 10. Phase 7 --- MCP Server and Read-Only Monitoring Tools

**Objective:** Expose AgentOps monitoring capabilities through a
well-defined MCP server.

### Tasks

1.  Use a maintained MCP SDK and follow its current server and transport
    conventions. Do not hand-roll the protocol.
2.  Keep the MCP server thin: it should call shared, authorized AgentOps
    service/query layers instead of duplicating database logic.
3.  Implement and document initial read-only tools, adjusting names to
    repository conventions:
    -   `list_agents`
    -   `get_agent_metrics`
    -   `list_runs`
    -   `get_run_details`
    -   `get_trace`
    -   `get_error_summary`
    -   `compare_runs`
4.  Define strict input schemas, required identifiers, default time
    ranges, maximum result sizes, and pagination.
5.  Return structured, predictable outputs suitable for an LLM client.
    Include source IDs/timestamps and explicit unavailable-data
    indicators.
6.  Apply authentication and authorization to every tool call. A caller
    must only access projects it is authorized to access.
7.  Validate time windows and prevent unbounded queries.
8.  Use read-only semantics. Do not add tools that execute arbitrary
    shell commands, code, SQL, agent tools, or production remediation.
9.  Provide safe error messages without leaking credentials, internal
    stack traces, or cross-tenant data.
10. Add an MCP client smoke test and examples for configuring a local
    MCP-compatible client.
11. Document transport and authentication configuration. Do not assume a
    specific client configuration format without verifying it.

### Tests

-   tool input validation;
-   valid structured tool responses;
-   unauthorized project access;
-   large/unbounded query rejection;
-   database/trace backend unavailable;
-   malformed IDs and time ranges;
-   tool output does not include secrets or unredacted payloads;
-   MCP protocol/client smoke test.

### Acceptance criteria

-   An MCP-compatible client can connect and list available tools.
-   Each tool returns actual AgentOps data through shared services.
-   Invalid requests return controlled errors.
-   Authorization and result limits apply consistently.
-   All tools remain read-only.

### Human verification checklist

-   Connect using the documented MCP client configuration.
-   Call every tool with a valid request.
-   Try invalid IDs and unauthorized project IDs.
-   Inspect output for schema consistency and sensitive data.
-   Confirm there is no unintended write or execution capability.

**Stop after Phase 7 and wait for explicit approval.**

------------------------------------------------------------------------

## 11. Phase 8 --- AI Diagnostic Assistant

**Objective:** Build a dedicated assistant that investigates telemetry
and explains likely causes using evidence.

### Tasks

1.  Define the assistant's role, tool permissions, context limits, and
    safe response format.
2.  Use the AgentOps MCP tools or shared query services to retrieve
    evidence; do not make the LLM the source of truth for metrics.
3.  Implement a bounded investigation workflow:
    -   understand the question and target agent/time range;
    -   retrieve relevant metrics and recent runs;
    -   identify anomalous/failed runs;
    -   inspect selected traces and error details;
    -   compare against a healthy baseline where possible;
    -   summarize evidence, hypotheses, confidence/uncertainty, and next
        checks.
4.  Require evidence references for material claims: run IDs, trace/span
    IDs, metric names, and time windows.
5.  Distinguish observations from hypotheses. For example, say "the
    traces show the retrieval span accounts for most of the observed
    duration" rather than asserting an unsupported root cause.
6.  Explain missing evidence and competing explanations where relevant.
7.  Add provider/model configuration through environment variables or
    the existing secrets mechanism.
8.  Set timeouts, bounded tool calls, maximum trace sizes, and
    token/context limits.
9.  Prevent prompt injection from telemetry fields: treat prompts, tool
    outputs, exception text, and user-controlled metadata as untrusted
    data, not instructions.
10. Do not pass secrets or full raw prompts to the LLM unless explicitly
    authorized and required; default to redacted summaries.
11. Keep the assistant read-only. No code changes, shell commands,
    database writes, infrastructure changes, or agent remediation.
12. Log diagnostic invocation metadata safely without storing
    unnecessary conversation secrets.
13. Create deterministic tests with mocked LLM responses and telemetry
    fixtures; add evaluation cases for known failures.

### Minimum diagnostic response structure

-   **Question/scope:** agent and time range investigated.
-   **Findings:** directly observed facts.
-   **Likely explanation:** ranked hypotheses are allowed only as
    diagnostic hypotheses, not as facts; explain evidence and
    uncertainty.
-   **Evidence:** linked run/span/metric references.
-   **What is unknown:** gaps or unavailable telemetry.
-   **Recommended next checks:** read-only steps for the developer.

### Tests

-   known slow LLM call;
-   slow tool/retrieval span;
-   provider error and retry behavior;
-   no evidence available;
-   conflicting or incomplete telemetry;
-   prompt-injection strings inside run metadata;
-   model timeout/rate limit;
-   assistant never claims it performed a remediation;
-   evidence references resolve to actual retrieved records.

### Acceptance criteria

-   The assistant answers using real retrieved telemetry.
-   It separates evidence from hypotheses and exposes uncertainty.
-   It does not invent run IDs, metrics, costs, or root causes.
-   It respects tenant access and privacy/redaction settings.
-   It cannot mutate monitored systems.

### Human verification checklist

-   Ask why a known test run failed.
-   Ask why a synthetic slow run was slow.
-   Ask a question for which no telemetry exists.
-   Insert malicious instruction text into a test event and confirm it
    is treated as data.
-   Verify every cited run/span/metric actually exists.
-   Confirm the assistant has no write-capable tools.

**Stop after Phase 8 and wait for explicit approval.**

------------------------------------------------------------------------

## 12. Phase 9 --- Security, Reliability, and Performance Hardening

**Objective:** Verify that AgentOps is safe to run alongside production
agents and reliable under failures.

### Tasks

1.  Perform a threat-model review covering SDK, ingestion, database,
    dashboard, MCP server, and diagnostic assistant.
2.  Verify authentication, authorization, tenant isolation, key
    rotation, and secret handling.
3.  Review logs, traces, metric labels, exception messages, and
    assistant context for sensitive data leakage.
4.  Apply rate limits and request/payload/query bounds.
5.  Test SDK behavior when DNS, network, backend, database, Prometheus,
    or trace backend is unavailable.
6.  Confirm retry policies are bounded, jittered where appropriate, and
    do not cause retry storms.
7.  Verify queue/buffer limits and behavior when the exporter is
    overwhelmed.
8.  Review database indexes and query plans for expected access
    patterns.
9.  Test ingestion and query performance with a documented synthetic
    workload.
10. Check Prometheus cardinality and memory behavior.
11. Test retention and deletion workflows, including consistency across
    metadata and trace storage.
12. Add dependency vulnerability scanning and secret scanning where
    available.
13. Add readiness/liveness checks and structured operational logs.
14. Document SLOs/targets only after agreeing on measurable thresholds;
    do not invent a guarantee based on local tests.
15. Produce a security and performance findings report with severity,
    evidence, and remediation status.

### Acceptance criteria

-   No known critical/high-severity issue introduced by the phase
    remains unresolved without explicit owner acceptance.
-   Cross-tenant access tests pass.
-   Sensitive-data controls work by default.
-   Telemetry outages do not normally break the monitored business
    operation.
-   Performance results include workload size, environment,
    measurements, and limitations.
-   Retention and deletion behavior are documented and tested.

### Human verification checklist

-   Review threat model and test report.
-   Inspect redaction and access-control tests.
-   Simulate telemetry backend outages.
-   Review resource limits and load-test results.
-   Approve any accepted residual risks explicitly.

**Stop after Phase 9 and wait for explicit approval.**

------------------------------------------------------------------------

## 13. Phase 10 --- Deployment, End-to-End Pilot, and Release Readiness

**Objective:** Deploy the MVP in a controlled environment and validate
the complete user journey.

### Tasks

1.  Review existing deployment targets and infrastructure decisions
    before selecting a production platform.
2.  Provide production-oriented container definitions and configuration
    without embedding secrets.
3.  Separate local development and production configuration.
4.  Configure HTTPS/reverse proxy and network boundaries where
    applicable.
5.  Add secret injection, backup/restore procedures, database
    migration/index steps, and trace/metrics retention configuration.
6.  Add CI checks for linting, typing, unit tests, integration tests,
    frontend build, and container build as supported.
7.  Write a runbook for startup, shutdown, upgrades, health checks,
    backup/restore, and incident troubleshooting.
8.  Deploy to a non-production environment first. Do not deploy to
    production or create paid resources without explicit authorization.
9.  Instrument one real or approved pilot agent.
10. Validate the complete path:
    -   agent execution;
    -   SDK export;
    -   authenticated ingestion;
    -   persisted run;
    -   Prometheus metric;
    -   trace backend record;
    -   dashboard run/trace view;
    -   MCP tool query;
    -   diagnostic assistant investigation.
11. Test failure cases, including agent exceptions, telemetry backend
    downtime, expired/invalid credentials, and unavailable trace data.
12. Record deployment environment, version, configuration, known
    limitations, and rollback procedure.
13. Produce a release-readiness report and a list of deferred non-MVP
    features.

### Acceptance criteria

-   A pilot agent is monitored end to end.
-   All required MVP user journeys work with real data.
-   CI checks pass or documented environment blocks are explicitly
    identified.
-   Secrets are not committed or exposed.
-   Backup/restore and rollback steps are documented.
-   The owner has enough evidence to approve or reject the MVP release.

### Human verification checklist

-   Follow the deployment runbook from a clean environment.
-   Integrate a pilot agent using the SDK documentation.
-   Verify metrics, traces, run history, MCP access, and diagnosis.
-   Validate failure behavior and authorization.
-   Review limitations, operational costs, and rollback procedure.

**Stop after Phase 10 and wait for explicit approval. Do not deploy to
production without a separate explicit authorization.**

------------------------------------------------------------------------

## 14. Definition of Done for Every Phase

A phase is ready for human review only when all applicable items below
are complete:

-   [ ] Phase scope is implemented and no later-phase scope has been
    started.
-   [ ] Code follows repository conventions and is reasonably modular.
-   [ ] Automated tests were added/updated.
-   [ ] Relevant tests were run and actual results recorded.
-   [ ] Lint, formatting, typing, and build checks were run where
    available.
-   [ ] Security/privacy implications were considered.
-   [ ] Configuration and `.env.example` are updated without secrets.
-   [ ] API/schema/docs/examples are updated where needed.
-   [ ] No unrelated user changes were overwritten.
-   [ ] `IMPLEMENTATION_STATUS.md` reflects the real status.
-   [ ] Manual verification checklist is specific and executable.
-   [ ] Known issues and unrun tests are disclosed.
-   [ ] Final status is `READY_FOR_REVIEW`, not `APPROVED`.

If a required check fails, fix it before review unless it is blocked by
an external dependency or environment. Clearly identify blockers rather
than hiding them.

------------------------------------------------------------------------

## 15. Required End-of-Phase Report Format

At the end of each phase, return a report in this format:

``` text
PHASE: <number and name>
STATUS: READY_FOR_REVIEW | BLOCKED

1. Summary
- What was implemented
- What was intentionally not implemented

2. Files changed
- Added:
- Modified:
- Removed: (explain why; should be rare)

3. Verification performed
- Command:
- Result:
- Notes:

4. Acceptance criteria
- [PASS/FAIL/BLOCKED] Criterion
- Evidence:

5. Known limitations / decisions needed
- ...

6. Human verification checklist
- [ ] ...
- [ ] ...

7. Status tracking
- IMPLEMENTATION_STATUS.md updated: yes/no
- Next phase: <number/name, NOT STARTED>

STOP: Waiting for explicit human approval before proceeding.
```

Never report `PASS` without evidence from an actual check. Keep the
report concise but sufficiently specific for independent verification.

------------------------------------------------------------------------

## 16. Initial Instructions When This File Is First Given to the Agent

When the human gives you this file for the first time:

1.  Read this entire file.
2.  Inspect repository instructions and the current Git working tree.
3.  Read the existing PRD/SRS and related architecture documents if
    present.
4.  Determine whether the repository is new, partially implemented, or
    already contains later-phase work.
5.  Report any conflicts between existing requirements and this plan.
6.  Begin **Phase 1 only** if no human-approved phase status already
    directs otherwise.
7.  Create/update the Phase 1 documentation and status file.
8.  Run only checks relevant to Phase 1.
9.  Deliver the Phase 1 review report and stop.

If the repository already has a completed phase, do not redo it
automatically. Compare it against that phase's acceptance criteria,
report evidence and gaps, and wait for the human to decide whether to
accept or revise it.

### Approval protocol

The human owner verifies each phase. The intended cycle is:

`Agent implements Phase N → Agent reports READY_FOR_REVIEW → Human tests/reviews → Human says APPROVE PHASE N → Agent may begin Phase N+1`

A request such as "fix this issue" keeps the agent within the current
phase. A request such as "continue" should be interpreted in the context
of the last review; if approval is ambiguous, ask before starting a new
phase.

------------------------------------------------------------------------

## 17. Assumptions and Decisions Register

Unless the PRD or human owner says otherwise, treat these as provisional
assumptions, not immutable requirements:

1.  The first SDK and adapter target Python.
2.  FastAPI is the backend framework.
3.  React + TypeScript is the dashboard framework if a dashboard is
    required and no frontend exists.
4.  Prometheus handles numeric time-series metrics.
5.  OpenTelemetry provides instrumentation/context and trace export.
6.  Grafana provides operational visualization.
7.  Tempo is the initial candidate for trace storage, subject to
    repository/environment review.
8.  MongoDB is the default candidate for run metadata/event persistence
    only if no existing database decision exists; otherwise reuse the
    approved database.
9.  The first release supports one framework adapter deeply rather than
    many adapters superficially.
10. The AI diagnostic assistant is read-only and evidence-based.
11. Prompt/output capture is off by default.
12. Production deployment, paid cloud resources, destructive migrations,
    and autonomous remediation require explicit human authorization.
13. Numeric SLOs, retention periods, sampling percentages, expected
    scale, and cost budgets must be agreed with the owner or recorded as
    provisional configuration. Do not invent them as commitments.

When a decision is made, record its date, rationale, alternatives
considered, and impact in `docs/assumptions-and-decisions.md`.

------------------------------------------------------------------------

## 18. Final Instruction

Implement AgentOps MCP as a maintainable product, not as a single demo
script. Keep the SDK, ingestion/query services, observability pipeline,
dashboard, MCP tools, and diagnostic assistant clearly separated while
sharing stable contracts.

**Most important: one phase per approval cycle. Do not implement the
next phase automatically. The human owner must be able to run, inspect,
test, and accept or reject every phase before work proceeds.**
