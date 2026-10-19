"""Read-only monitoring tools for the AgentOps MCP server (Phase 7).

This module is deliberately independent of the MCP protocol library: it is a
thin, authorised wrapper over the same query layers the REST API and the
dashboard use (``queries`` and ``trace_service``). The protocol adapter lives
in ``mcp_server.py``.

Guarantees
----------
* Every call authenticates the presented API key (``read`` scope) against the
  database, so revoked keys stop working immediately.
* A caller only ever reaches the project its key belongs to. An explicit
  ``project_id`` argument that differs from the key's project is rejected.
* Time windows are validated and bounded; list results are capped.
* Output is structured and sanitised: run metadata, raw event payloads and
  payload summaries are never returned unless the operator enabled
  ``AGENTOPS_PAYLOAD_CAPTURE_ENABLED``; free-text fields are truncated.
* No tool writes data or executes anything.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Callable, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from agentops_backend import queries, trace_service
from agentops_backend.auth import Principal, authenticate, require_project_access
from agentops_backend.config import Settings
from agentops_backend.errors import ApiError, unauthorized
from agentops_backend.schemas import SAFE_ID_PATTERN

logger = logging.getLogger("agentops_backend.mcp")

_ID_RE = re.compile(SAFE_ID_PATTERN)
_RUN_STATUSES = {"running", "success", "error", "cancelled", "unknown"}
_ENVIRONMENTS = {"development", "staging", "production"}
MAX_TEXT_LEN = 256
MAX_SPANS = 200
DEFAULT_SPANS = 100
DATA_SOURCE = "agentops_run_store"


class ToolError(Exception):
    """A controlled, safe-to-return tool failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:  # what the MCP client sees
        return f"{self.code}: {self.message}"


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #
def _check_id(value: Optional[str], name: str, *, required: bool = False) -> Optional[str]:
    if value is None or value == "":
        if required:
            raise ToolError("invalid_argument", f"'{name}' is required.")
        return None
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise ToolError(
            "invalid_argument",
            f"'{name}' must be 1-64 characters of letters, digits, '_', '.' or '-'.",
        )
    return value


def _parse_time(value: Optional[str], name: str) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > 64:
        raise ToolError("invalid_time_range", f"'{name}' must be an ISO-8601 timestamp.")
    text = value.strip()
    if text.endswith(("Z", "z")):  # datetime.fromisoformat rejects 'Z' before 3.11
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        raise ToolError("invalid_time_range", f"'{name}' must be an ISO-8601 timestamp.")
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _paging(page: int, page_size: Optional[int], cap: int) -> tuple[int, int]:
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ToolError("invalid_argument", "'page' must be an integer >= 1.")
    size = cap if page_size is None else page_size
    if isinstance(size, bool) or not isinstance(size, int) or size < 1 or size > cap:
        raise ToolError("invalid_argument", f"'page_size' must be an integer between 1 and {cap}.")
    return page, size


def _text(value: Optional[str]) -> Optional[str]:
    return None if value is None else str(value)[:MAX_TEXT_LEN]


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
class MonitoringTools:
    """Authorised, read-only tool implementations."""

    def __init__(self, settings: Settings, session_factory: Callable[[], Session]) -> None:
        self.settings = settings
        self.session_factory = session_factory

    # ---- plumbing ---------------------------------------------------------- #
    def _principal(self, session: Session, token: Optional[str]) -> Principal:
        if not token:
            raise unauthorized()
        shim = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(settings=self.settings)), headers={}
        )
        principal = authenticate(shim, session, token=token)  # type: ignore[arg-type]
        if "read" not in principal.scopes:
            raise ApiError(403, "insufficient_scope", "API key lacks the 'read' scope.")
        return principal

    def _window(
        self, started_after: Optional[str], started_before: Optional[str]
    ) -> tuple[datetime, datetime]:
        after = _parse_time(started_after, "started_after")
        before = _parse_time(started_before, "started_before")
        now = datetime.now(timezone.utc)
        if before is None:
            before = now
        if after is None:
            after = before - timedelta(hours=self.settings.mcp_default_window_hours)
        if after >= before:
            raise ToolError(
                "invalid_time_range", "'started_after' must be earlier than 'started_before'."
            )
        if before - after > timedelta(days=self.settings.mcp_max_window_days):
            raise ToolError(
                "time_range_too_large",
                f"Time window may not exceed {self.settings.mcp_max_window_days} days.",
            )
        return after, before

    def _run(
        self,
        token: Optional[str],
        project_id: Optional[str],
        fn: Callable[[Session, Principal], dict],
    ) -> dict:
        """Authenticate, authorise, execute ``fn`` and map every failure to a
        controlled ``ToolError`` (no stack traces, SQL or secrets)."""
        try:
            _check_id(project_id, "project_id")
            with self.session_factory() as session:
                principal = self._principal(session, token)
                if project_id is not None:
                    require_project_access(principal, project_id)
                result = fn(session, principal)
                result["source"] = {
                    "project_id": principal.project_id,
                    "data_source": DATA_SOURCE,
                    "generated_at": _iso(datetime.now(timezone.utc)),
                }
                return result
        except ToolError:
            raise
        except ApiError as exc:
            raise ToolError(exc.code, exc.message) from None
        except SQLAlchemyError as exc:
            logger.error("MCP storage error: %s", type(exc).__name__)
            raise ToolError("storage_unavailable", "Storage is temporarily unavailable.") from None
        except Exception as exc:  # never leak internals to the client
            logger.error("MCP internal error: %s", type(exc).__name__)
            raise ToolError("internal_error", "An internal error occurred.") from None

    # ---- shaping ----------------------------------------------------------- #
    def _run_summary(self, r) -> dict[str, Any]:
        out: dict[str, Any] = {
            "run_id": r.run_id,
            "agent_id": r.agent_id,
            "environment": r.environment,
            "status": r.status,
            "started_at": _iso(r.started_at),
            "ended_at": _iso(r.ended_at),
            "duration_ms": r.duration_ms,
            "error_type": _text(r.error_type),
            "error_summary": _text(r.error_summary),
            "deployment_version": r.deployment_version,
            "llm_call_count": r.llm_call_count,
            "tool_call_count": r.tool_call_count,
            "total_prompt_tokens": r.total_prompt_tokens,
            "total_completion_tokens": r.total_completion_tokens,
            "total_tokens": r.total_tokens,
            "trace_id": r.trace_id,
        }
        if self.settings.payload_capture_enabled and r.metadata:
            out["metadata"] = r.metadata
        return out

    @staticmethod
    def _window_out(after: datetime, before: datetime) -> dict:
        return {"started_after": _iso(after), "started_before": _iso(before)}

    # ---- tools ------------------------------------------------------------- #
    def list_agents(
        self, token: Optional[str], project_id: Optional[str] = None,
        page: int = 1, page_size: Optional[int] = None,
    ) -> dict:
        page, size = _paging(page, page_size, self.settings.mcp_max_results)

        def fn(session: Session, principal: Principal) -> dict:
            agents = queries.list_agents(session, principal.project_id)
            chunk = agents[(page - 1) * size : page * size]
            return {
                "kind": "summary",
                "items": [
                    {
                        "agent_id": a.id,
                        "name": a.name,
                        "auto_registered": a.auto_registered,
                        "run_count": a.run_count,
                        "last_run_at": _iso(a.last_run_at),
                    }
                    for a in chunk
                ],
                "total": len(agents),
                "page": page,
                "page_size": size,
                "truncated": page * size < len(agents),
            }

        return self._run(token, project_id, fn)

    def get_agent_metrics(
        self, token: Optional[str], agent_id: str, project_id: Optional[str] = None,
        started_after: Optional[str] = None, started_before: Optional[str] = None,
    ) -> dict:
        _check_id(agent_id, "agent_id", required=True)
        after, before = self._window(started_after, started_before)

        def fn(session: Session, principal: Principal) -> dict:
            m = queries.agent_metrics(
                session, principal.project_id, agent_id,
                started_after=after, started_before=before,
            )
            unavailable = []
            if m["duration_ms"]["p50"] is None:
                unavailable.append("duration_ms: no finished runs with a duration in window")
            if m["error_rate"] is None:
                unavailable.append("error_rate: no finished runs in window")
            return {
                "kind": "summary",
                "agent_id": agent_id,
                "window": self._window_out(after, before),
                "metrics": m,
                "unavailable": unavailable,
            }

        return self._run(token, project_id, fn)

    def list_runs(
        self, token: Optional[str], project_id: Optional[str] = None,
        agent_id: Optional[str] = None, status: Optional[str] = None,
        environment: Optional[str] = None,
        started_after: Optional[str] = None, started_before: Optional[str] = None,
        page: int = 1, page_size: Optional[int] = None,
    ) -> dict:
        _check_id(agent_id, "agent_id")
        if status is not None and status not in _RUN_STATUSES:
            raise ToolError(
                "invalid_argument", f"'status' must be one of {sorted(_RUN_STATUSES)}."
            )
        if environment is not None and environment not in _ENVIRONMENTS:
            raise ToolError(
                "invalid_argument", f"'environment' must be one of {sorted(_ENVIRONMENTS)}."
            )
        page, size = _paging(page, page_size, self.settings.mcp_max_results)
        after, before = self._window(started_after, started_before)

        def fn(session: Session, principal: Principal) -> dict:
            res = queries.list_runs(
                session, principal.project_id, agent_id=agent_id, status=status,
                environment=environment, started_after=after, started_before=before,
                page=page, page_size=size,
            )
            return {
                "kind": "summary",
                "window": self._window_out(after, before),
                "items": [self._run_summary(r) for r in res.items],
                "total": res.total,
                "page": res.page,
                "page_size": res.page_size,
                "truncated": res.page * res.page_size < res.total,
            }

        return self._run(token, project_id, fn)

    def get_run_details(
        self, token: Optional[str], run_id: str, project_id: Optional[str] = None
    ) -> dict:
        _check_id(run_id, "run_id", required=True)

        def fn(session: Session, principal: Principal) -> dict:
            detail = queries.get_run_detail(session, principal.project_id, run_id)
            counts: dict[str, int] = {}
            for e in detail.events:
                counts[e.event_type] = counts.get(e.event_type, 0) + 1
            return {
                "kind": "summary",
                "run": self._run_summary(detail.run),
                "event_count": detail.event_count,
                "event_type_counts": counts,
                "events_truncated": detail.events_truncated,
                "note": "Raw event payloads are not returned; use get_trace for spans.",
            }

        return self._run(token, project_id, fn)

    def get_trace(
        self, token: Optional[str], run_id: str, project_id: Optional[str] = None,
        max_spans: int = DEFAULT_SPANS,
    ) -> dict:
        _check_id(run_id, "run_id", required=True)
        if isinstance(max_spans, bool) or not isinstance(max_spans, int) \
                or not 1 <= max_spans <= MAX_SPANS:
            raise ToolError(
                "invalid_argument", f"'max_spans' must be an integer between 1 and {MAX_SPANS}."
            )

        def fn(session: Session, principal: Principal) -> dict:
            t = trace_service.get_run_timeline(
                session, principal.project_id, run_id,
                include_payload_summary=False,  # never return payload summaries over MCP
                max_spans=max_spans, event_page=1, event_page_size=1,
                otlp_base_url=self.settings.otlp_ui_base_url,
                trace_retention_days=self.settings.trace_retention_days,
                run_retention_days=self.settings.run_retention_days,
            )
            spans = []
            for s in t.spans:
                attrs = {
                    k: (_text(v) if isinstance(v, str) else v) for k, v in s.attributes.items()
                }
                spans.append({
                    "span_id": s.span_id,
                    "parent_span_id": s.parent_span_id,
                    "name": _text(s.name),
                    "event_type": s.event_type,
                    "start_time": _iso(s.start_time),
                    "end_time": _iso(s.end_time),
                    "duration_ms": s.duration_ms,
                    "status": s.status,
                    "parent_missing": s.parent_missing,
                    "attributes": attrs,
                })
            unavailable = []
            if t.trace_data_may_have_expired:
                unavailable.append(
                    "external_trace_backend: trace may have expired; local spans shown"
                )
            return {
                "kind": "detail",
                "run": self._run_summary(t.run),
                "trace_id": t.run.trace_id,
                "is_complete": t.is_complete,
                "trace_data_may_have_expired": t.trace_data_may_have_expired,
                "span_count": len(spans),
                "spans": spans,
                "spans_truncated": t.spans_truncated,
                "unavailable": unavailable,
            }

        return self._run(token, project_id, fn)

    def get_error_summary(
        self, token: Optional[str], project_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        started_after: Optional[str] = None, started_before: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> dict:
        _check_id(agent_id, "agent_id")
        cap = self.settings.mcp_max_results
        if limit is None:
            limit = cap
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= cap:
            raise ToolError("invalid_argument", f"'limit' must be an integer between 1 and {cap}.")
        after, before = self._window(started_after, started_before)

        def fn(session: Session, principal: Principal) -> dict:
            s = queries.error_summary(
                session, principal.project_id, agent_id=agent_id,
                started_after=after, started_before=before, limit=limit,
            )
            return {
                "kind": "summary",
                "window": self._window_out(after, before),
                "total_runs": s.total_runs,
                "error_runs": s.error_runs,
                "error_rate": (s.error_runs / s.total_runs) if s.total_runs else None,
                "groups": [
                    {
                        "agent_id": g.agent_id,
                        "error_type": _text(g.error_type),
                        "count": g.count,
                        "last_seen": _iso(g.last_seen),
                    }
                    for g in s.groups
                ],
                "groups_truncated": len(s.groups) >= limit,
            }

        return self._run(token, project_id, fn)

    def compare_runs(
        self, token: Optional[str], run_id_a: str, run_id_b: str,
        project_id: Optional[str] = None,
    ) -> dict:
        _check_id(run_id_a, "run_id_a", required=True)
        _check_id(run_id_b, "run_id_b", required=True)

        def fn(session: Session, principal: Principal) -> dict:
            a = queries.get_run_detail(session, principal.project_id, run_id_a, 1).run
            b = queries.get_run_detail(session, principal.project_id, run_id_b, 1).run

            def delta(x: Optional[int], y: Optional[int]) -> Optional[int]:
                return None if x is None or y is None else y - x

            return {
                "kind": "summary",
                "run_a": self._run_summary(a),
                "run_b": self._run_summary(b),
                "comparison": {
                    "same_agent": a.agent_id == b.agent_id,
                    "status_changed": a.status != b.status,
                    "error_type_changed": a.error_type != b.error_type,
                    "deltas_b_minus_a": {
                        "duration_ms": delta(a.duration_ms, b.duration_ms),
                        "llm_call_count": delta(a.llm_call_count, b.llm_call_count),
                        "tool_call_count": delta(a.tool_call_count, b.tool_call_count),
                        "total_tokens": delta(a.total_tokens, b.total_tokens),
                    },
                },
                "unavailable": [
                    "duration_ms delta: a run has no recorded duration"
                ] if a.duration_ms is None or b.duration_ms is None else [],
            }

        return self._run(token, project_id, fn)
