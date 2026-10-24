"""OpenTelemetry trace pipeline.

How traces are produced
-----------------------
SDK-instrumented agents report *events*, not spans. The backend materialises
spans from accepted events, re-using the identifiers already stored on the run:

* ``agent.run``  – root span; ``trace_id``/``span_id`` are the run's
  ``trace_id``/``root_span_id`` so Tempo traces correlate 1:1 with run history.
* ``llm.*`` / ``tool.*`` – child spans of the root, one per completed/failed
  call (start = event time minus reported ``duration_ms`` when available).

Ingestion requests additionally get a live ``ingest.batch`` span (a separate
trace) created through a normal OTel tracer.

Safety properties
-----------------
* Export is asynchronous through a bounded ``BatchSpanProcessor`` queue; when
  the queue is full spans are dropped by the SDK instead of blocking ingestion.
* Exporter failures are caught, logged without payloads, and counted in
  ``agentops_trace_export_failures_total``; they never reach the request path.
* Sampling: spans of error runs / error calls are *always* exported. Other
  spans are exported with probability ``trace_sample_ratio`` decided
  deterministically from the trace id. Limitation: with a ratio below 1.0 the
  non-error children of an unsampled run that later fails are not exported
  (their parent root span and the failing span are).
* Only identifiers, names, and bounded scalar attributes are attached; prompts,
  outputs, and secrets are never span attributes.
"""
from __future__ import annotations

import contextlib
import logging
from datetime import datetime, timezone
from typing import Iterator, Mapping, Optional, Sequence

from opentelemetry import trace as otel_trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.trace import SpanContext, SpanKind, Status, StatusCode, TraceFlags

from marg_backend import __version__
from marg_backend.config import Settings
from marg_backend.metrics import Metrics

logger = logging.getLogger(__name__)

SCOPE = InstrumentationScope("marg.backend", __version__)
MAX_ATTR_LEN = 256


class ResilientExporter(SpanExporter):
    """Wrap an exporter so failures are observable but never raise."""

    def __init__(self, inner: SpanExporter, metrics: Metrics) -> None:
        self._inner = inner
        self._metrics = metrics

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            result = self._inner.export(spans)
        except Exception as exc:  # noqa: BLE001 - exporter must never raise
            logger.warning("Trace export failed: %s", type(exc).__name__)
            self._metrics.trace_export_failures_total.inc()
            return SpanExportResult.FAILURE
        if result is not SpanExportResult.SUCCESS:
            logger.warning("Trace export returned %s", result)
            self._metrics.trace_export_failures_total.inc()
        return result

    def shutdown(self) -> None:
        try:
            self._inner.shutdown()
        except Exception:  # noqa: BLE001
            logger.warning("Trace exporter shutdown failed")

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        try:
            return self._inner.force_flush(timeout_millis)
        except Exception:  # noqa: BLE001
            return False


def _ns(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1_000_000_000)


def _clip(value: object) -> str:
    return str(value)[:MAX_ATTR_LEN]


def _valid_ids(trace_id: str, span_id: str) -> Optional[tuple[int, int]]:
    try:
        t, s = int(trace_id, 16), int(span_id, 16)
    except (TypeError, ValueError):
        return None
    if t == 0 or s == 0:
        return None
    return t, s


class SpanPipeline:
    """Owns the tracer provider, processor and sampling policy."""

    def __init__(
        self,
        settings: Settings,
        metrics: Metrics,
        exporter: Optional[SpanExporter] = None,
    ) -> None:
        self._metrics = metrics
        self._ratio = settings.trace_sample_ratio
        self.enabled = False
        self._provider: Optional[TracerProvider] = None
        self._processor: Optional[BatchSpanProcessor] = None
        self._tracer: Optional[otel_trace.Tracer] = None

        if exporter is None and settings.otlp_endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(
                endpoint=settings.otlp_endpoint,
                timeout=settings.trace_export_timeout_seconds,
            )
        if exporter is None:
            return

        self._resource = Resource.create(
            {"service.name": settings.service_name, "service.version": __version__}
        )
        self._processor = BatchSpanProcessor(
            ResilientExporter(exporter, metrics),
            max_queue_size=settings.trace_queue_size,
            export_timeout_millis=settings.trace_export_timeout_seconds * 1000,
        )
        self._provider = TracerProvider(
            resource=self._resource,
            sampler=ParentBased(TraceIdRatioBased(self._ratio)),
        )
        self._provider.add_span_processor(self._processor)
        self._tracer = self._provider.get_tracer("marg.backend", __version__)
        self.enabled = True

    # ----------------------------- sampling -------------------------------- #
    def sampled(self, trace_id: str) -> bool:
        """Deterministic head decision from the trace id (1.0 => always)."""
        if self._ratio >= 1.0:
            return True
        if self._ratio <= 0.0:
            return False
        try:
            bucket = int(trace_id[:16], 16) / float(1 << 64)
        except ValueError:
            return False
        return bucket < self._ratio

    # ------------------------------ emission ------------------------------- #
    def emit(
        self,
        *,
        name: str,
        trace_id: str,
        span_id: str,
        parent_span_id: Optional[str],
        start: datetime,
        end: datetime,
        attributes: Mapping[str, object],
        error: bool = False,
        error_description: Optional[str] = None,
    ) -> bool:
        """Queue one finished span. Returns True if it was handed to the exporter."""
        if not self.enabled or self._processor is None:
            return False
        if not error and not self.sampled(trace_id):
            self._metrics.trace_spans_total.labels(outcome="sampled_out").inc()
            return False
        ids = _valid_ids(trace_id, span_id)
        if ids is None:
            self._metrics.trace_spans_total.labels(outcome="invalid_ids").inc()
            return False
        flags = TraceFlags(TraceFlags.SAMPLED)
        context = SpanContext(ids[0], ids[1], is_remote=False, trace_flags=flags)
        parent = None
        if parent_span_id:
            pid = _valid_ids(trace_id, parent_span_id)
            if pid is not None:
                parent = SpanContext(ids[0], pid[1], is_remote=False, trace_flags=flags)
        status = (
            Status(StatusCode.ERROR, _clip(error_description or "error"))
            if error
            else Status(StatusCode.OK)
        )
        span = ReadableSpan(
            name=name,
            context=context,
            parent=parent,
            resource=self._resource,
            attributes={k: _clip(v) for k, v in attributes.items() if v is not None},
            kind=SpanKind.INTERNAL,
            status=status,
            start_time=_ns(start),
            end_time=max(_ns(end), _ns(start)),
            instrumentation_scope=SCOPE,
        )
        self._processor.on_end(span)
        self._metrics.trace_spans_total.labels(outcome="queued").inc()
        return True

    @contextlib.contextmanager
    def ingest_span(self, project_id: str) -> Iterator[Optional[otel_trace.Span]]:
        """Live span for one ingestion request (no-op when tracing is disabled)."""
        if not self.enabled or self._tracer is None:
            yield None
            return
        with self._tracer.start_as_current_span(
            "ingest.batch", attributes={"marg.project_id": _clip(project_id)}
        ) as span:
            yield span

    # ------------------------------- control ------------------------------- #
    def force_flush(self, timeout_millis: int = 5000) -> bool:
        if self._processor is None:
            return True
        return self._processor.force_flush(timeout_millis)

    def shutdown(self) -> None:
        if self._provider is not None:
            try:
                self._provider.shutdown()
            except Exception:  # noqa: BLE001
                logger.warning("Tracer provider shutdown failed")
