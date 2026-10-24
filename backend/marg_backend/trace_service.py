"""Trace and run-history service for Phase 5.

Responsibility
--------------
This module assembles the explainable timeline for a single run.  It works
exclusively from the data that the backend already owns (the ``runs`` and
``events`` tables) and presents it as an ordered, annotated span timeline that
does not require the external OTLP trace store (Tempo) to be reachable.

Design decisions
----------------
* **No external dependency at read time.**  Tempo / any OTLP backend is
  write-only from this service's perspective.  A caller can optionally ask for
  an external trace link, but the timeline is always served from local storage.
* **Span assembly from events.**  Each accepted event carries the identifiers
  needed to reconstruct the parent-child relationship: ``trace_id``,
  ``root_span_id``, ``span_id`` (child), ``parent_span_id``.  The service
  assembles spans in timestamp order and applies parent resolution so the
  relationship tree is presented correctly even when spans arrive late.
* **Incomplete trace detection.**  A run whose ``ended_at`` is NULL, or whose
  last event is not a terminal event, is reported as incomplete.  Missing
  parent spans (a child references a span_id that has no corresponding event)
  are flagged individually.
* **Privacy.**  Input/output summaries are only included when
  ``AGENTOPS_PAYLOAD_CAPTURE_ENABLED=true`` (default False).  All other
  span attributes contain only identifiers, names, and bounded scalars.
* **Pagination.**  Span lists and event lists are always bounded; callers must
  paginate large runs.

Retention contract
------------------
The local ``runs`` / ``events`` tables retain data for
``AGENTOPS_RUN_RETENTION_DAYS`` days (default 90).  External OTLP traces may
have a shorter retention (default 30 days via Tempo ``block_retention: 720h``).
After the OTLP trace window expires the run record and its events remain
queryable via this service; the ``trace_link`` field will still point to the
Tempo query URL but Tempo itself may return nothing.  The API communicates this
via the ``trace_data_may_have_expired`` boolean on the run-detail response.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from marg_backend.errors import not_found
from marg_backend.models import Event, Run
from marg_backend.schemas import (
    EventOut,
    RunOut,
)

logger = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────── #
MAX_SPANS_PER_TRACE = 1000
MAX_EVENTS_PER_PAGE = 500
SPAN_ID_RE = re.compile(r"^[0-9a-f]{16}$")
TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")

# Event types that mark the beginning of an operation (used for span timing).
_START_TYPES = frozenset(
    {"llm_call_started", "tool_call_started", "run_started", "custom_event"}
)
# Event types that finish the root span.
_TERMINAL_TYPES = frozenset({"run_completed", "run_failed", "run_cancelled"})
# Event types that produce child spans.
_CHILD_TYPES = frozenset(
    {
        "llm_call_completed",
        "llm_call_failed",
        "tool_call_completed",
        "tool_call_failed",
    }
)


# ── helpers ───────────────────────────────────────────────────────────────── #

def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _derive_span_id(project_id: str, event_id: str) -> str:
    """Deterministic fallback span-id matching the one used at ingest time."""
    return hashlib.sha256(f"span:{project_id}:{event_id}".encode()).hexdigest()[:16]


def _safe(value: Any, *, max_len: int = 256) -> Optional[str]:
    if value is None:
        return None
    return str(value)[:max_len]


def _bool_data(data: dict, key: str) -> bool:
    return bool(data.get(key))


def _int_data(data: dict, key: str) -> Optional[int]:
    v = data.get(key)
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


# ── span assembly ─────────────────────────────────────────────────────────── #

def _event_to_span_info(event: Event, project_id: str) -> "SpanInfo":
    """Convert one stored Event to an intermediate SpanInfo for assembly."""
    data: dict = event.data or {}
    et = event.event_type
    ts = _aware(event.timestamp)
    assert ts is not None

    # Resolve span identity
    span_id = data.get("span_id") if SPAN_ID_RE.match(str(data.get("span_id") or "")) else None
    if span_id is None:
        # Use deterministic fallback (same formula as observability.py)
        span_id = _derive_span_id(project_id, event.event_id)

    parent_span_id = (
        data.get("parent_span_id")
        if SPAN_ID_RE.match(str(data.get("parent_span_id") or ""))
        else None
    )

    # Duration
    duration_ms = _int_data(data, "duration_ms")
    start_time = ts - timedelta(milliseconds=duration_ms or 0)

    # Status
    if et in ("llm_call_failed", "tool_call_failed", "run_failed"):
        status = "error"
    elif et in ("run_completed", "llm_call_completed", "tool_call_completed"):
        status = "ok"
    elif et == "run_cancelled":
        status = "cancelled"
    else:
        status = "ok"

    # Span name
    if et in ("llm_call_completed", "llm_call_failed", "llm_call_started"):
        op = _safe(data.get("operation_name")) or "llm.chat"
        name = op
    elif et in ("tool_call_completed", "tool_call_failed", "tool_call_started"):
        tool = _safe(data.get("tool_name")) or "call"
        name = f"tool.{tool}"
    elif et in ("run_started", "run_completed", "run_failed", "run_cancelled"):
        name = "agent.run"
    else:
        name = _safe(data.get("operation_name")) or et

    # Safe attributes (no prompts/secrets)
    attrs: dict[str, Any] = {
        "event_type": et,
        "agent_id": event.agent_id,
        "environment": event.environment,
    }
    if data.get("provider"):
        attrs["llm.provider"] = _safe(data["provider"])
    if data.get("model"):
        attrs["llm.model"] = _safe(data["model"])
    if data.get("tool_name"):
        attrs["tool.name"] = _safe(data["tool_name"])
    if data.get("tool_type"):
        attrs["tool.type"] = _safe(data["tool_type"])
    pt = _int_data(data, "prompt_tokens")
    ct = _int_data(data, "completion_tokens")
    tt = _int_data(data, "total_tokens")
    if pt is not None:
        attrs["llm.prompt_tokens"] = pt
    if ct is not None:
        attrs["llm.completion_tokens"] = ct
    if tt is not None:
        attrs["llm.total_tokens"] = tt
    if status == "error":
        attrs["error.type"] = _safe(data.get("error_type")) or "error"
        attrs["error.summary"] = _safe(data.get("error_summary"))

    return SpanInfo(
        span_id=span_id,
        parent_span_id=parent_span_id,
        name=name,
        event_id=event.event_id,
        event_type=et,
        start_time=start_time,
        end_time=ts,
        duration_ms=duration_ms,
        status=status,
        attributes=attrs,
    )


class SpanInfo:
    """Assembled in-memory representation of one span in the run timeline."""

    __slots__ = (
        "span_id", "parent_span_id", "name", "event_id", "event_type",
        "start_time", "end_time", "duration_ms", "status", "attributes",
        "parent_missing",
    )

    def __init__(
        self,
        span_id: str,
        parent_span_id: Optional[str],
        name: str,
        event_id: str,
        event_type: str,
        start_time: datetime,
        end_time: datetime,
        duration_ms: Optional[int],
        status: str,
        attributes: dict,
    ) -> None:
        self.span_id = span_id
        self.parent_span_id = parent_span_id
        self.name = name
        self.event_id = event_id
        self.event_type = event_type
        self.start_time = start_time
        self.end_time = end_time
        self.duration_ms = duration_ms
        self.status = status
        self.attributes = attributes
        self.parent_missing = False  # set during resolution


# ── public query functions ─────────────────────────────────────────────────── #

def get_run_timeline(
    session: Session,
    project_id: str,
    run_id: str,
    *,
    include_payload_summary: bool = False,
    max_spans: int = MAX_SPANS_PER_TRACE,
    event_page: int = 1,
    event_page_size: int = MAX_EVENTS_PER_PAGE,
    otlp_base_url: Optional[str] = None,
    trace_retention_days: int = 30,
    run_retention_days: int = 90,
) -> "RunTimelineResult":
    """
    Assemble the full explainable timeline for one run.

    Parameters
    ----------
    include_payload_summary:
        When False (default) event data is returned without prompt/response
        payloads — these are always stripped.  When True, ``summary`` fields
        may be included if they were captured at ingest time.
    max_spans:
        Hard cap on spans returned.  Spans are ordered by start_time; the
        earliest are returned and the rest are indicated by ``spans_truncated``.
    event_page / event_page_size:
        Pagination for the raw event list (independent from span truncation).
    otlp_base_url:
        Base URL of the Tempo / Jaeger UI (e.g. ``http://localhost:3000``).
        When set, ``trace_link`` is populated with a deep-link.
    trace_retention_days:
        How long the OTLP backend keeps traces.  Used to compute
        ``trace_data_may_have_expired``.
    run_retention_days:
        How long this service keeps run records.  Surfaced in correlation_links.
    """
    run = session.get(Run, (project_id, run_id))
    if run is None:
        raise not_found("Run not found.")

    max_spans = max(1, min(max_spans, MAX_SPANS_PER_TRACE))
    event_page_size = max(1, min(event_page_size, MAX_EVENTS_PER_PAGE))
    event_page = max(1, event_page)

    # ── fetch events chronologically (stable: timestamp ASC, event_id ASC) ── #
    total_event_count = session.execute(
        select(func.count())
        .select_from(Event)
        .where(Event.project_id == project_id, Event.run_id == run_id)
    ).scalar_one()

    all_events = (
        session.execute(
            select(Event)
            .where(Event.project_id == project_id, Event.run_id == run_id)
            .order_by(Event.timestamp, Event.event_id)
        )
        .scalars()
        .all()
    )

    # ── build span list ──────────────────────────────────────────────────── #
    known_span_ids: set[str] = set()
    spans: list[SpanInfo] = []

    # Root span from run record (always present, even if incomplete)
    root_start = _aware(run.started_at)
    root_end = _aware(run.ended_at) or _aware(run.updated_at)
    assert root_start is not None and root_end is not None
    root_span = SpanInfo(
        span_id=run.root_span_id,
        parent_span_id=None,
        name="agent.run",
        event_id="",
        event_type="run_started",
        start_time=root_start,
        end_time=root_end,
        duration_ms=run.duration_ms,
        status=(
            "error" if run.status == "error"
            else "cancelled" if run.status == "cancelled"
            else "ok" if run.status == "success"
            else "running"
        ),
        attributes={
            "marg.run_id": run.run_id,
            "marg.agent_id": run.agent_id,
            "marg.environment": run.environment,
            "marg.run_status": run.status,
            "marg.llm_call_count": run.llm_call_count,
            "marg.tool_call_count": run.tool_call_count,
            "marg.total_tokens": run.total_tokens,
            **({"error.type": run.error_type} if run.error_type else {}),
        },
    )
    known_span_ids.add(run.root_span_id)
    spans.append(root_span)

    # Child spans from events
    for event in all_events:
        if event.event_type not in _CHILD_TYPES:
            continue
        if len(spans) >= max_spans:
            break
        si = _event_to_span_info(event, project_id)
        if si.span_id not in known_span_ids:
            known_span_ids.add(si.span_id)
            spans.append(si)

    # ── parent resolution pass ─────────────────────────────────────────── #
    for si in spans[1:]:  # root never needs resolution
        if si.parent_span_id is None:
            si.parent_span_id = run.root_span_id  # default to root
        elif si.parent_span_id not in known_span_ids:
            si.parent_missing = True  # parent span not in this result set

    spans_truncated = len(all_events) > 0 and len(spans) >= max_spans and (
        sum(1 for e in all_events if e.event_type in _CHILD_TYPES) > max_spans - 1
    )

    # ── trace completeness ─────────────────────────────────────────────── #
    has_terminal = any(e.event_type in _TERMINAL_TYPES for e in all_events)
    is_complete = has_terminal and run.ended_at is not None

    # ── event page (raw events) ────────────────────────────────────────── #
    paged_events = all_events[
        (event_page - 1) * event_page_size : event_page * event_page_size
    ]

    # ── payload stripping ─────────────────────────────────────────────── #
    _PAYLOAD_KEYS = frozenset(
        {"summary", "output_summary", "input_summary", "result_summary"}
    )

    def _strip_event(event: Event) -> EventOut:
        data = dict(event.data or {})
        if not include_payload_summary:
            for k in _PAYLOAD_KEYS:
                data.pop(k, None)
        return EventOut(
            event_id=event.event_id,
            run_id=event.run_id,
            agent_id=event.agent_id,
            event_type=event.event_type,
            environment=event.environment,
            timestamp=_aware(event.timestamp),  # type: ignore[arg-type]
            data=data,
        )

    # ── correlation links ─────────────────────────────────────────────── #
    now_utc = datetime.now(timezone.utc)
    run_start_aware = _aware(run.started_at)
    assert run_start_aware is not None
    trace_expires_at = run_start_aware + timedelta(days=trace_retention_days)
    run_expires_at = run_start_aware + timedelta(days=run_retention_days)
    trace_data_may_have_expired = now_utc > trace_expires_at

    correlation_links: dict[str, Any] = {
        "run_id": run.run_id,
        "trace_id": run.trace_id,
        "root_span_id": run.root_span_id,
        "run_metadata_expires_at": run_expires_at.isoformat(),
        "trace_data_expires_at": trace_expires_at.isoformat(),
    }
    if run.started_at and run.ended_at:
        # Inclusive metric time window with 1-minute padding
        metric_start = (run_start_aware - timedelta(minutes=1)).isoformat()
        metric_end = ((_aware(run.ended_at) or now_utc) + timedelta(minutes=1)).isoformat()
        correlation_links["metric_window"] = {
            "from": metric_start,
            "to": metric_end,
        }
    trace_link: Optional[str] = None
    if otlp_base_url and TRACE_ID_RE.match(run.trace_id):
        trace_link = f"{otlp_base_url.rstrip('/')}/explore?traceId={run.trace_id}"

    from marg_backend.schemas import RunOut
    run_out = _run_to_out(run)

    return RunTimelineResult(
        run=run_out,
        is_complete=is_complete,
        trace_data_may_have_expired=trace_data_may_have_expired,
        spans=spans,
        spans_truncated=spans_truncated,
        total_event_count=total_event_count,
        events=[_strip_event(e) for e in paged_events],
        event_page=event_page,
        event_page_size=event_page_size,
        trace_link=trace_link,
        correlation_links=correlation_links,
    )


def get_run_by_trace_id(
    session: Session,
    project_id: str,
    trace_id: str,
) -> "Run":
    """Look up a run by its OpenTelemetry trace_id (scoped to the project)."""
    if not TRACE_ID_RE.match(trace_id):
        raise not_found("Invalid trace_id format.")
    row = session.execute(
        select(Run).where(
            Run.project_id == project_id,
            Run.trace_id == trace_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found("No run found for this trace_id.")
    return row


# ── result container ──────────────────────────────────────────────────────── #

class RunTimelineResult:
    """Non-Pydantic holder; serialised to ``RunTimelineOut`` at the route layer."""

    __slots__ = (
        "run", "is_complete", "trace_data_may_have_expired",
        "spans", "spans_truncated",
        "total_event_count", "events", "event_page", "event_page_size",
        "trace_link", "correlation_links",
    )

    def __init__(
        self,
        run: RunOut,
        is_complete: bool,
        trace_data_may_have_expired: bool,
        spans: list[SpanInfo],
        spans_truncated: bool,
        total_event_count: int,
        events: list[EventOut],
        event_page: int,
        event_page_size: int,
        trace_link: Optional[str],
        correlation_links: dict,
    ) -> None:
        self.run = run
        self.is_complete = is_complete
        self.trace_data_may_have_expired = trace_data_may_have_expired
        self.spans = spans
        self.spans_truncated = spans_truncated
        self.total_event_count = total_event_count
        self.events = events
        self.event_page = event_page
        self.event_page_size = event_page_size
        self.trace_link = trace_link
        self.correlation_links = correlation_links


# ── helpers (kept out of schemas to avoid circular import) ────────────────── #

def _run_to_out(r: Run) -> RunOut:
    from marg_backend.schemas import RunOut
    return RunOut(
        run_id=r.run_id,
        agent_id=r.agent_id,
        project_id=r.project_id,
        trace_id=r.trace_id,
        root_span_id=r.root_span_id,
        environment=r.environment,
        status=r.status,
        started_at=_aware(r.started_at),  # type: ignore[arg-type]
        ended_at=_aware(r.ended_at),
        duration_ms=r.duration_ms,
        error_type=r.error_type,
        error_summary=r.error_summary,
        deployment_version=r.deployment_version,
        sdk_version=r.sdk_version,
        llm_call_count=r.llm_call_count,
        tool_call_count=r.tool_call_count,
        total_prompt_tokens=r.total_prompt_tokens,
        total_completion_tokens=r.total_completion_tokens,
        total_tokens=r.total_tokens,
        metadata=r.run_metadata,
        created_at=_aware(r.created_at),  # type: ignore[arg-type]
        updated_at=_aware(r.updated_at),  # type: ignore[arg-type]
    )
