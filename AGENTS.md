# AgentOps MCP — Coding Agent Instructions

## Purpose
Implement AgentOps MCP according to `implementation.md` and the approved PRD/SRS and architecture decisions in this repository.

## Mandatory workflow
1. Before coding, read this file, `implementation.md`, applicable PRD/SRS and architecture docs, and any repository/tool-specific instructions.
2. Inspect the current Git working tree and preserve all existing user changes.
3. Read `PROGRESS.md` and `IMPLEMENTATION_STATUS.md` before deciding what to do.
4. Implement only the currently authorized phase from `implementation.md`.
5. Do not start the next phase automatically. At the end of a phase, stop at `READY_FOR_REVIEW` and wait for explicit human approval.
6. Do not mark any phase `APPROVED` unless the human owner explicitly approved that phase. Record the approval accurately.
7. If the owner requests fixes, remain in the current phase unless they explicitly authorize progression.
8. If existing implementation is present, assess it against the phase acceptance criteria before changing it. Do not redo completed work blindly.
9. If a decision is not blocking, use the documented provisional defaults and record the assumption. Ask a focused question only when a safe, material decision cannot be resolved from the repository or requirements.

## Required progress tracking
- `PROGRESS.md` is the chronological work log. Append a dated entry for each meaningful work session, recording changes, commands and actual results, tests, blockers, decisions, and the next permitted action.
- `IMPLEMENTATION_STATUS.md` is the concise current-state snapshot. Keep it synchronized with `PROGRESS.md`.
- Update both files after each work session and at phase completion.
- Never fabricate test results, implementation status, human approvals, deployment outcomes, or telemetry data.
- Record checks that could not run as `BLOCKED` or `NOT RUN`, with the reason.
- Keep a checklist for all ten phases and preserve history rather than rewriting past sessions.

## Engineering and safety rules
- Follow the existing architecture and repository conventions where sound. Avoid unrelated refactors and unnecessary dependencies.
- Never expose or commit credentials, API keys, tokens, `.env` contents, customer prompts, or private production payloads. Keep real secrets out of examples and logs.
- Maintain `.env.example` with placeholders only.
- Treat telemetry as sensitive: payload capture should be off by default, redaction must be supported, and sensitive content must not be placed in Prometheus labels.
- Avoid high-cardinality metric labels such as run IDs, user IDs, raw prompts, or arbitrary exception messages.
- Telemetry collection should be bounded and best-effort by default so an observability outage does not normally break the monitored agent.
- Do not run destructive migrations, delete user data, provision paid cloud resources, deploy to production, or perform autonomous remediation without explicit authorization.
- Do not represent mocks, stubs, or synthetic data as production functionality.
- Keep public schemas and interfaces documented and tested.

## Phase completion gate
Before requesting review:
1. Run relevant tests, linting, formatting, type checks, and builds available in the repository.
2. Fix issues caused by the changes, or document genuine blockers.
3. Update relevant docs and examples.
4. Append the work session to `PROGRESS.md`.
5. Refresh `IMPLEMENTATION_STATUS.md`.
6. Provide the end-of-phase report and executable manual verification checklist required by `implementation.md`.
7. Set status to `READY_FOR_REVIEW`, never self-approve.
8. Stop and wait.

## First-run behavior
On first use, inspect the repository and requirements, reconcile any existing agent instructions, and execute Phase 1 only. Do not begin Phase 2 until the human owner explicitly approves Phase 1.
