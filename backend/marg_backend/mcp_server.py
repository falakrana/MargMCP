"""AgentOps MCP server (Phase 7): read-only monitoring tools over MCP.

Run (stdio, default; the client launches the process)::

    python -m marg_backend.mcp_server

Run over streamable HTTP (binds to 127.0.0.1 by default)::

    python -m marg_backend.mcp_server --transport streamable-http --port 8765

Authentication
--------------
Every tool call is authenticated with an AgentOps API key that has the
``read`` scope.

* stdio: the key is taken from ``AGENTOPS_MCP_API_KEY`` in the server process
  environment.
* streamable-http: the per-request ``Authorization: Bearer <key>`` header is
  used; ``AGENTOPS_MCP_API_KEY`` is only a fallback.

The key fixes the project the caller can see. See ``docs/mcp-server.md``.
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Any, Callable, Optional

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError as McpToolError
from mcp.types import ToolAnnotations
from sqlalchemy.orm import Session

from marg_backend.assistant import DiagnosticEngine, build_provider
from marg_backend.config import Settings, get_settings
from marg_backend.db import make_engine, make_session_factory
from marg_backend.errors import ApiError
from marg_backend.mcp_tools import DEFAULT_SPANS, MonitoringTools, ToolError

logger = logging.getLogger("marg_backend.mcp")

TOOL_NAMES = (
    "list_agents",
    "get_agent_metrics",
    "list_runs",
    "get_run_details",
    "get_trace",
    "get_error_summary",
    "compare_runs",
)

# Phase 8: read-only AI diagnostics (calls an external LLM when configured).
DIAGNOSTIC_TOOL_NAMES = ("diagnose_run", "diagnose_agent")

_READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
_DIAGNOSTIC = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=False, openWorldHint=True
)


def _bearer_from_context(ctx: Optional[Context]) -> Optional[str]:
    """Return the bearer token from the HTTP request, if the transport has one."""
    try:
        request = ctx.request_context.request  # type: ignore[union-attr]
        header = request.headers.get("authorization", "") if request is not None else ""
    except Exception:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return None


def build_server(
    settings: Optional[Settings] = None,
    session_factory: Optional[Callable[[], Session]] = None,
    **fastmcp_kwargs: Any,
) -> FastMCP:
    settings = settings or get_settings()
    if session_factory is None:
        session_factory = make_session_factory(
            make_engine(settings.resolved_database_url(), settings)
        )
    tools = MonitoringTools(settings, session_factory)
    mcp = FastMCP(
        "marg",
        instructions=(
            "Read-only Marg MCP observability tools. All results are scoped to the "
            "project of the configured API key. Times are UTC ISO-8601. Results are "
            "summaries unless a tool says 'detail'; list tools are paginated and capped."
        ),
        **fastmcp_kwargs,
    )

    def token_for(ctx: Optional[Context]) -> Optional[str]:
        return _bearer_from_context(ctx) or settings.mcp_api_key

    def call(fn: Callable[..., dict], *args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return fn(*args, **kwargs)
        except ToolError as exc:
            raise McpToolError(str(exc)) from None

    @mcp.tool(annotations=_READ_ONLY)
    def list_agents(
        ctx: Context, project_id: Optional[str] = None, page: int = 1,
        page_size: Optional[int] = None,
    ) -> dict[str, Any]:
        """List agents in the caller's project (summary, paginated).

        project_id is optional; if given it must match the API key's project.
        """
        return call(tools.list_agents, token_for(ctx), project_id, page, page_size)

    @mcp.tool(annotations=_READ_ONLY)
    def get_agent_metrics(
        ctx: Context, agent_id: str, project_id: Optional[str] = None,
        started_after: Optional[str] = None, started_before: Optional[str] = None,
    ) -> dict[str, Any]:
        """Aggregate metrics for one agent (summary): run counts by status, error
        rate, duration avg/p50/p95/max, LLM/tool call counts and token totals.

        Window is half-open [started_after, started_before) in ISO-8601; default is
        the last 24 hours; the maximum window is 30 days.
        """
        return call(
            tools.get_agent_metrics, token_for(ctx), agent_id, project_id,
            started_after, started_before,
        )

    @mcp.tool(annotations=_READ_ONLY)
    def list_runs(
        ctx: Context, project_id: Optional[str] = None, agent_id: Optional[str] = None,
        status: Optional[str] = None, environment: Optional[str] = None,
        started_after: Optional[str] = None, started_before: Optional[str] = None,
        page: int = 1, page_size: Optional[int] = None,
    ) -> dict[str, Any]:
        """Search run history (summary, newest first, paginated and capped).

        status: running|success|error|cancelled|unknown. environment:
        development|staging|production. Default window is the last 24 hours.
        """
        return call(
            tools.list_runs, token_for(ctx), project_id, agent_id, status, environment,
            started_after, started_before, page, page_size,
        )

    @mcp.tool(annotations=_READ_ONLY)
    def get_run_details(
        ctx: Context, run_id: str, project_id: Optional[str] = None
    ) -> dict[str, Any]:
        """Summary of one run (status, timing, tokens, error type) with event-type
        counts. Raw event payloads are never returned."""
        return call(tools.get_run_details, token_for(ctx), run_id, project_id)

    @mcp.tool(annotations=_READ_ONLY)
    def get_trace(
        ctx: Context, run_id: str, project_id: Optional[str] = None,
        max_spans: int = DEFAULT_SPANS,
    ) -> dict[str, Any]:
        """Detail: bounded span tree for one run (parent/child, status, duration,
        completeness flags). Prompts and outputs are never included."""
        return call(tools.get_trace, token_for(ctx), run_id, project_id, max_spans)

    @mcp.tool(annotations=_READ_ONLY)
    def get_error_summary(
        ctx: Context, project_id: Optional[str] = None, agent_id: Optional[str] = None,
        started_after: Optional[str] = None, started_before: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> dict[str, Any]:
        """Summary: failed runs grouped by agent and error type, most frequent
        first. Default window is the last 24 hours."""
        return call(
            tools.get_error_summary, token_for(ctx), project_id, agent_id,
            started_after, started_before, limit,
        )

    @mcp.tool(annotations=_READ_ONLY)
    def compare_runs(
        ctx: Context, run_id_a: str, run_id_b: str, project_id: Optional[str] = None
    ) -> dict[str, Any]:
        """Summary: side-by-side comparison of two runs in the same project with
        deltas (b minus a) for duration, LLM calls, tool calls and tokens."""
        return call(tools.compare_runs, token_for(ctx), run_id_a, run_id_b, project_id)

    diagnostics = DiagnosticEngine(settings, session_factory, build_provider(settings))

    def diagnose(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return fn(*args, **kwargs).model_dump(mode="json")
        except ApiError as exc:
            raise McpToolError(f"{exc.code}: {exc.message}") from None

    @mcp.tool(annotations=_DIAGNOSTIC)
    def diagnose_run(
        ctx: Context, run_id: str, project_id: Optional[str] = None,
        question: Optional[str] = None,
    ) -> dict[str, Any]:
        """AI-assisted, read-only diagnosis of one run. Retrieves evidence through the
        other tools' data layer and returns findings (facts), likely explanations
        (hypotheses with confidence), cited evidence, unknowns and next checks. Every
        statement cites a retrieved run/span/metric. Needs the assistant configured."""
        return diagnose(
            diagnostics.diagnose_run, token_for(ctx), run_id,
            project_id=project_id, question=question,
        )

    @mcp.tool(annotations=_DIAGNOSTIC)
    def diagnose_agent(
        ctx: Context, agent_id: str, project_id: Optional[str] = None,
        started_after: Optional[str] = None, started_before: Optional[str] = None,
        question: Optional[str] = None,
    ) -> dict[str, Any]:
        """AI-assisted, read-only diagnosis of an agent's recent failures and latency
        (default window last 24 hours, max 30 days). Same report format and
        evidence guarantees as diagnose_run."""
        return diagnose(
            diagnostics.diagnose_agent, token_for(ctx), agent_id,
            project_id=project_id, started_after=started_after,
            started_before=started_before, question=question,
        )

    return mcp


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Marg MCP server (read-only)")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    # stdio uses stdout for the protocol; all logging must go to stderr.
    logging.basicConfig(level=get_settings().log_level.upper(), stream=sys.stderr)
    settings = get_settings()
    if args.transport == "stdio" and not settings.mcp_api_key:
        logger.error("AGENTOPS_MCP_API_KEY is not set; every tool call will be rejected.")
    server = build_server(settings, host=args.host, port=args.port)
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
