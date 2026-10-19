# AgentOps MCP Server (Phase 7)

A read-only [Model Context Protocol](https://modelcontextprotocol.io) server that exposes AgentOps
monitoring data to MCP-compatible clients. It is built on the official Python MCP SDK (`mcp`,
`FastMCP`) and is a thin layer over the same query services the REST API and dashboard use
(`queries.py`, `trace_service.py`). No database logic is duplicated.

> **Read-only.** There is no tool that writes data, runs shell commands, code, SQL, agent tools or
> remediation. Every tool is annotated `readOnlyHint=true`.

## Running

```powershell
# stdio (default): the MCP client launches this process
$env:AGENTOPS_MCP_API_KEY = "<read-scoped AgentOps API key>"
python -m agentops_backend.mcp_server        # or: agentops-mcp

# streamable HTTP (binds to 127.0.0.1 by default)
python -m agentops_backend.mcp_server --transport streamable-http --port 8765
```

The server needs the same database settings as the backend (`AGENTOPS_DATABASE_URL` or
`POSTGRES_*`) and the same `AGENTOPS_SECRET_KEY` (used to verify API keys).

stdio uses stdout for the protocol, so all server logging goes to stderr.

## Authentication and authorisation

* Every tool call is authenticated against the database with an AgentOps API key that has the
  **`read`** scope. Revoking a key takes effect on the next call.
* **stdio:** the key comes from `AGENTOPS_MCP_API_KEY` in the server process environment.
* **streamable-http:** the per-request `Authorization: Bearer <key>` header is used;
  `AGENTOPS_MCP_API_KEY` is only a fallback. Do not expose this transport beyond localhost without
  TLS and a reverse proxy.
* A key belongs to one project; the caller can only see that project. Every tool accepts an optional
  `project_id`; if it differs from the key's project the call fails with `project_access_denied`.
* Create a key with the admin API (`POST /v1/admin/projects/{id}/api-keys`, scopes `["read"]`).
  Keys are never logged or returned by any tool.

## Configuration

| Variable                              | Default     | Meaning                                         |
| ------------------------------------- | ----------- | ----------------------------------------------- |
| `AGENTOPS_MCP_API_KEY`              | _(unset)_ | Read-scoped key for stdio / fallback for HTTP   |
| `AGENTOPS_MCP_DEFAULT_WINDOW_HOURS` | `24`      | Window used when a time range is omitted        |
| `AGENTOPS_MCP_MAX_WINDOW_DAYS`      | `30`      | Wider windows are rejected                      |
| `AGENTOPS_MCP_MAX_RESULTS`          | `50`      | Max rows for list-style tools (1–100)          |
| `AGENTOPS_PAYLOAD_CAPTURE_ENABLED`  | `false`   | Run `metadata` is only returned when `true` |

## Tools

All times are UTC ISO-8601 (`2026-10-19T08:00:00Z`; a missing offset is treated as UTC). Windows are
half-open: `started_after <= started_at < started_before`. IDs match `^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$`.
Every successful response includes `kind` (`summary` or `detail`) and
`source` = `{project_id, data_source, generated_at}`. Fields that cannot be computed are `null` and
explained in an `unavailable` list.

| Tool                  | Kind    | Inputs (required in **bold**)                                                             | Notes                                                                        |
| --------------------- | ------- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `list_agents`       | summary | `project_id?`, `page=1`, `page_size?`                                                     | Agents with run counts and last run                                          |
| `get_agent_metrics` | summary | **`agent_id`**, `project_id?`, `started_after?`, `started_before?`                | Runs by status, error rate, duration avg/p50/p95/max, LLM/tool calls, tokens |
| `list_runs`         | summary | `project_id?`, `agent_id?`, `status?`, `environment?`, window, `page`, `page_size?` | Newest first; `status` ∈ running/success/error/cancelled/unknown          |
| `get_run_details`   | summary | **`run_id`**, `project_id?`                                                           | Run summary + event-type counts. No raw events                               |
| `get_trace`         | detail  | **`run_id`**, `project_id?`, `max_spans=100` (1–200)                               | Bounded span tree, completeness and expiry flags                             |
| `get_error_summary` | summary | `project_id?`, `agent_id?`, window, `limit?`                                              | Failures grouped by agent and error type                                     |
| `compare_runs`      | summary | **`run_id_a`**, **`run_id_b`**, `project_id?`                                 | Both summaries + deltas (b − a)                                             |

### Errors

Failures are returned as MCP tool errors (`isError: true`) whose text is `<code>: <message>`.
Messages never contain stack traces, SQL, connection strings or other tenants' data.

| Code                      | Cause                                                         |
| ------------------------- | ------------------------------------------------------------- |
| `unauthorized`          | Missing, malformed, unknown or revoked key                    |
| `insufficient_scope`    | Key lacks the `read` scope                                  |
| `project_access_denied` | `project_id` differs from the key's project                 |
| `invalid_argument`      | Malformed ID, bad enum, page/limit out of range               |
| `invalid_time_range`    | Unparseable timestamp, or `started_after >= started_before` |
| `time_range_too_large`  | Window exceeds `AGENTOPS_MCP_MAX_WINDOW_DAYS`               |
| `not_found`             | Run/agent does not exist **in the caller's project**    |
| `storage_unavailable`   | Database error                                                |
| `internal_error`        | Anything unexpected (details are logged by type only)         |

### Output safety

* Raw event payloads, run `metadata` (unless payload capture is enabled) and payload summaries are
  never returned; `get_trace` always strips summaries regardless of the capture setting.
* Free text (`error_summary`, span names/attributes) is truncated to 256 characters.
* Large traces are bounded by `max_spans`; `spans_truncated` tells the client more exist.
* Timeouts: tool calls are synchronous bounded queries; there is no tool that runs unbounded work.

## Client configuration

> The MCP client configuration format differs between clients and versions. The JSON below follows
> the widely used `mcpServers` convention (e.g. Claude Desktop, Cursor). Verify the exact file
> location and schema in your client's documentation before relying on it.

```json
{
  "mcpServers": {
    "agentops": {
      "command": "C:\\path\\to\\AgentOpsMCP\\.venv\\Scripts\\python.exe",
      "args": ["-m", "agentops_backend.mcp_server"],
      "env": {
        "AGENTOPS_DATABASE_URL": "postgresql+psycopg://user:password@localhost:5432/agentops",
        "AGENTOPS_SECRET_KEY": "<same value as the backend>",
        "AGENTOPS_MCP_API_KEY": "<read-scoped AgentOps API key>"
      }
    }
  }
}
```

Inspect the server interactively with the official inspector:

```powershell
npx @modelcontextprotocol/inspector python -m agentops_backend.mcp_server
```

## Tests

`backend/tests/test_mcp.py` covers input validation, structured outputs, unauthorised and
cross-project access, bounded queries, storage failure, sanitisation, read-only surface, and a real
MCP client ⇄ server smoke test over stdio:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_mcp.py -q
```

## Manual verification checklist

1. Create a read-scoped key and start the server (or configure your MCP client as above).
2. List tools: expect exactly the seven tools above, all read-only.
3. Call each tool with valid arguments against seeded data (`python -m agentops_backend.seed`).
4. Call with an invalid ID (`../x`), a reversed/huge time window and `page_size=1000`: expect
   controlled `invalid_argument` / `invalid_time_range` / `time_range_too_large` errors.
5. Call with another project's `project_id` and with an ingest-only key: expect
   `project_access_denied` / `insufficient_scope`.
6. Inspect outputs for secrets, prompts and payloads: there should be none.
7. Confirm no tool can write or execute anything.
