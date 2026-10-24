"""Glue between ingestion and the metrics / trace pipelines.

``Observability.record_batch`` is invoked once per ingested batch *after* the
database transaction committed. It is strictly best-effort: any exception is
swallowed (and counted) so an observability fault can never fail ingestion or
change what was stored.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Optional, Sequence

from opentelemetry.sdk.trace.export import SpanExporter

from marg_backend.config import Settings
from marg_backend.metrics import Metrics
from marg_backend.tracing import SpanPipeline

logger = logging.getLogger(__name__)

INGEST_ENDPOINT = "/v1/telemetry/events"
_NAME_UNSAFE = re.compile(r"[^A-Za-z0-9_.\-/:]")


@dataclass(frozen=True)
class EventObservation:
    """Immutable view of one *newly accepted* event plus its run's state."""

    project_id: str
    event_id: str
    run_id: str
    agent_id: str
    event_type: str
    environment: str
    timestamp: datetime
    data: dict[str, Any]
    trace_id: str
    root_span_id: str
    run_status: str
    run_started_at: datetime
    run_ended_at: Optional[datetime]
    run_duration_ms: Optional[int]
    run_error_type: Optional[str]
    terminal_transition: bool  # run became terminal because of this event
    duration_became_known: bool  # run duration first became computable here


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _safe_name(value: object, default: str) -> str:
    text = _NAME_UNSAFE.sub("_", str(value or "").strip())[:64]
    return text or default


def _span_id(project_id: str, event_id: str) -> str:
    return hashlib.sha256(f"span:{project_id}:{event_id}".encode()).hexdigest()[:16]


def _int(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


class Observability:
    def __init__(
        self,
        settings: Settings,
        metrics: Optional[Metrics] = None,
        span_exporter: Optional[SpanExporter] = None,
    ) -> None:
        self.metrics = metrics or Metrics()
        self.tracing = SpanPipeline(settings, self.metrics, exporter=span_exporter)

    # --------------------------- request level ----------------------------- #
    def observe_request(self, endpoint: str, status_code: int, seconds: float) -> None:
        try:
            self.metrics.ingestion_requests_total.labels(
                status=str(status_code), endpoint=endpoint
            ).inc()
            self.metrics.ingestion_latency.labels(endpoint=endpoint).observe(seconds)
        except Exception:  # noqa: BLE001
            self._swallow("request")

    @contextmanager
    def ingest_span(self, project_id: str) -> Iterator[Any]:
        try:
            cm = self.tracing.ingest_span(project_id)
            span = cm.__enter__()
        except Exception:  # noqa: BLE001
            self._swallow("ingest_span")
            yield None
            return
        try:
            yield span
        except BaseException as exc:
            try:
                cm.__exit__(type(exc), exc, exc.__traceback__)
            except Exception:  # noqa: BLE001
                self._swallow("ingest_span")
            raise
        else:
            try:
                cm.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                self._swallow("ingest_span")

    # ---------------------------- batch level ------------------------------ #
    def record_batch(
        self,
        events: Sequence[EventObservation],
        duplicates: int,
        rejected_codes: Sequence[str],
    ) -> None:
        try:
            m = self.metrics
            if events:
                m.events_total.labels(outcome="accepted").inc(len(events))
            if duplicates:
                m.events_total.labels(outcome="duplicate").inc(duplicates)
            if rejected_codes:
                m.events_total.labels(outcome="rejected").inc(len(rejected_codes))
                for code in rejected_codes:
                    m.events_rejected_total.labels(code=m.code(code)).inc()
        except Exception:  # noqa: BLE001
            self._swallow("batch_counters")

        for obs in events:
            try:
                self._record_event(obs)
            except Exception:  # noqa: BLE001
                self._swallow("event")

    # ------------------------------ internals ------------------------------ #
    def _record_event(self, obs: EventObservation) -> None:
        m = self.metrics
        agent = m.agent(obs.agent_id)
        et = obs.event_type
        data = obs.data

        if et in ("llm_call_completed", "llm_call_failed"):
            status = "ok" if et == "llm_call_completed" else "error"
            provider, model = m.provider(data.get("provider")), m.model(data.get("model"))
            llm_agent, provider, model = m.llm_series((agent, provider, model))
            m.llm_calls_total.labels(
                agent_id=llm_agent, provider=provider, model=model, status=status
            ).inc()
            duration_ms = _int(data.get("duration_ms"))
            if duration_ms is not None:
                m.llm_call_duration.labels(
                    agent_id=llm_agent, provider=provider, model=model
                ).observe(duration_ms / 1000)
            if et == "llm_call_completed":
                for key, kind in (("prompt_tokens", "prompt"), ("completion_tokens", "completion")):
                    value = _int(data.get(key))
                    if value:
                        m.tokens_total.labels(
                            agent_id=llm_agent, provider=provider, model=model, token_type=kind
                        ).inc(value)
            self._child_span(obs, "llm.chat", duration_ms, error=status == "error", attrs={
                "llm.provider": data.get("provider"),
                "llm.model": data.get("model"),
                "llm.prompt_tokens": data.get("prompt_tokens"),
                "llm.completion_tokens": data.get("completion_tokens"),
                "llm.total_tokens": data.get("total_tokens"),
            })
        elif et in ("tool_call_completed", "tool_call_failed"):
            status = "ok" if et == "tool_call_completed" else "error"
            tool = m.tool(data.get("tool_name"))
            tool_agent, tool = m.tool_series((agent, tool))
            m.tool_calls_total.labels(agent_id=tool_agent, tool_name=tool, status=status).inc()
            duration_ms = _int(data.get("duration_ms"))
            if duration_ms is not None:
                m.tool_call_duration.labels(agent_id=tool_agent, tool_name=tool).observe(
                    duration_ms / 1000
                )
            self._child_span(
                obs, f"tool.{_safe_name(data.get('tool_name'), 'call')}", duration_ms,
                error=status == "error",
                attrs={"tool.name": data.get("tool_name"), "tool.type": data.get("tool_type")},
            )

        if obs.terminal_transition:
            m.runs_total.labels(
                agent_id=agent, environment=obs.environment, status=obs.run_status
            ).inc()
        if obs.duration_became_known and obs.run_duration_ms is not None:
            m.run_duration.labels(agent_id=agent, environment=obs.environment).observe(
                obs.run_duration_ms / 1000
            )
            self._root_span(obs)

    def _common_attrs(self, obs: EventObservation) -> dict[str, object]:
        return {
            "marg.project_id": obs.project_id,
            "marg.agent_id": obs.agent_id,
            "marg.run_id": obs.run_id,
            "marg.environment": obs.environment,
        }

    def _root_span(self, obs: EventObservation) -> None:
        if obs.run_ended_at is None:
            return
        failed = obs.run_status == "error"
        attrs = self._common_attrs(obs)
        attrs["marg.run_status"] = obs.run_status
        if failed:
            attrs["error.type"] = obs.run_error_type or "UnknownError"
        self.tracing.emit(
            name="agent.run",
            trace_id=obs.trace_id,
            span_id=obs.root_span_id,
            parent_span_id=None,
            start=_aware(obs.run_started_at),
            end=_aware(obs.run_ended_at),
            attributes=attrs,
            error=failed,
            error_description=obs.run_error_type,
        )

    def _child_span(
        self,
        obs: EventObservation,
        default_name: str,
        duration_ms: Optional[int],
        *,
        error: bool,
        attrs: dict[str, object],
    ) -> None:
        end = _aware(obs.timestamp)
        start = end - timedelta(milliseconds=duration_ms or 0)
        data = obs.data
        span_id = data.get("span_id") if isinstance(data.get("span_id"), str) else None
        parent = data.get("parent_span_id") if isinstance(data.get("parent_span_id"), str) else None
        merged = self._common_attrs(obs)
        merged.update(attrs)
        self.tracing.emit(
            name=_safe_name(data.get("operation_name"), default_name),
            trace_id=obs.trace_id,
            span_id=span_id or _span_id(obs.project_id, obs.event_id),
            parent_span_id=parent or obs.root_span_id,
            start=start,
            end=end,
            attributes=merged,
            error=error,
            error_description=obs.event_type,
        )

    def _swallow(self, where: str) -> None:
        logger.warning("Observability error in %s (ignored)", where, exc_info=False)
        try:
            self.metrics.observability_errors_total.inc()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------- control ------------------------------- #
    def shutdown(self) -> None:
        self.tracing.shutdown()


def timer() -> float:
    return time.perf_counter()
