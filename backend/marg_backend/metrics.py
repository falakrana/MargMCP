"""Prometheus metric definitions (docs/telemetry-schema.md §7).

Label policy
------------
Every label is either a fixed enumeration (``status``, ``outcome``,
``token_type``, ``environment``) or passes through :class:`BoundedLabel`,
which sanitises the value and caps the number of distinct values it will ever
emit (overflow collapses into ``"other"``). Run IDs, event IDs, user IDs, trace
IDs, prompts and exception messages are never used as labels.

A dedicated registry (not the global default) is used so each application
instance owns its metrics; this keeps tests isolated and avoids duplicate
registration errors.
"""
from __future__ import annotations

import re
import threading

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from marg_backend import __version__

_UNSAFE = re.compile(r"[^A-Za-z0-9_.\-/:]")

RUN_DURATION_BUCKETS = (0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600)
CALL_DURATION_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60)
REQUEST_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)


class BoundedLabel:
    """Sanitise a label value and bound how many distinct values can exist."""

    OVERFLOW = "other"

    def __init__(self, max_values: int, max_len: int = 64) -> None:
        self._max_values = max_values
        self._max_len = max_len
        self._seen: set[str] = set()
        self._lock = threading.Lock()

    def __call__(self, value: object) -> str:
        text = "" if value is None else str(value).strip()
        text = _UNSAFE.sub("_", text)[: self._max_len]
        if not text:
            return "unknown"
        with self._lock:
            if text in self._seen:
                return text
            if len(self._seen) >= self._max_values:
                return self.OVERFLOW
            self._seen.add(text)
            return text


class SeriesCap:
    """Bound the number of distinct label *combinations* a metric family emits.

    Per-label caps multiply: 200 agents x 50 providers x 100 models would allow
    one million series per metric. This caps the product; once full, unseen
    combinations collapse to ``other`` for every label.
    """

    def __init__(self, max_series: int) -> None:
        self._max = max_series
        self._seen: set[tuple[str, ...]] = set()
        self._lock = threading.Lock()

    def __call__(self, key: tuple[str, ...]) -> tuple[str, ...]:
        with self._lock:
            if key in self._seen:
                return key
            if len(self._seen) >= self._max:
                return tuple(BoundedLabel.OVERFLOW for _ in key)
            self._seen.add(key)
            return key

    def __len__(self) -> int:
        return len(self._seen)


class Metrics:
    """All backend metrics, bound to a private registry."""

    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        r = self.registry

        self.agent = BoundedLabel(max_values=200)
        self.provider = BoundedLabel(max_values=50)
        self.model = BoundedLabel(max_values=100)
        self.tool = BoundedLabel(max_values=100)
        self.code = BoundedLabel(max_values=50)
        # Combination caps (see SeriesCap). Worst case per family stays in the
        # low tens of thousands of series instead of millions.
        self.llm_series = SeriesCap(max_series=2000)
        self.tool_series = SeriesCap(max_series=2000)

        self.runs_total = Counter(
            "marg_runs_total", "Runs reaching a terminal status.",
            ["agent_id", "environment", "status"], registry=r,
        )
        self.run_duration = Histogram(
            "marg_run_duration_seconds", "Run duration distribution.",
            ["agent_id", "environment"], buckets=RUN_DURATION_BUCKETS, registry=r,
        )
        self.llm_calls_total = Counter(
            "marg_llm_calls_total", "LLM calls observed.",
            ["agent_id", "provider", "model", "status"], registry=r,
        )
        self.llm_call_duration = Histogram(
            "marg_llm_call_duration_seconds", "LLM call latency (when reported).",
            ["agent_id", "provider", "model"], buckets=CALL_DURATION_BUCKETS, registry=r,
        )
        self.tool_calls_total = Counter(
            "marg_tool_calls_total", "Tool calls observed.",
            ["agent_id", "tool_name", "status"], registry=r,
        )
        self.tool_call_duration = Histogram(
            "marg_tool_call_duration_seconds", "Tool call latency (when reported).",
            ["agent_id", "tool_name"], buckets=CALL_DURATION_BUCKETS, registry=r,
        )
        self.tokens_total = Counter(
            "marg_tokens_total", "Token usage.",
            ["agent_id", "provider", "model", "token_type"], registry=r,
        )
        self.ingestion_requests_total = Counter(
            "marg_ingestion_requests_total", "Ingestion API requests.",
            ["status", "endpoint"], registry=r,
        )
        self.ingestion_latency = Histogram(
            "marg_ingestion_latency_seconds", "Ingestion API latency.",
            ["endpoint"], buckets=REQUEST_BUCKETS, registry=r,
        )
        self.events_total = Counter(
            "marg_events_total", "Telemetry events by ingestion outcome.",
            ["outcome"], registry=r,
        )
        self.events_rejected_total = Counter(
            "marg_events_rejected_total", "Rejected telemetry events by rejection code.",
            ["code"], registry=r,
        )
        self.trace_spans_total = Counter(
            "marg_trace_spans_total", "Spans handled by the trace pipeline.",
            ["outcome"], registry=r,
        )
        self.trace_export_failures_total = Counter(
            "marg_trace_export_failures_total",
            "Failed trace export attempts (exporter errors never break ingestion).",
            registry=r,
        )
        self.observability_errors_total = Counter(
            "marg_observability_errors_total",
            "Internal errors while recording metrics/spans (swallowed).",
            registry=r,
        )
        self.rate_limited_total = Counter(
            "marg_rate_limited_total",
            "Requests rejected with 429, by limiter scope.",
            ["scope"], registry=r,
        )
        self.build_info = Gauge(
            "marg_backend_info", "Backend build information.", ["version"], registry=r,
        )
        self.build_info.labels(version=__version__).set(1)
