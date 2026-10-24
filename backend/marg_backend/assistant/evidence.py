"""Bounded evidence retrieval for the diagnostic assistant.

Evidence is gathered ONLY through :class:`MonitoringTools` (the authorised,
read-only Phase 7 tool layer), so tenant scoping, validation, payload
redaction and result caps apply exactly as they do for MCP clients. The LLM
never chooses queries and never supplies evidence.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from marg_backend.config import Settings
from marg_backend.mcp_tools import MonitoringTools, ToolError

MAX_TEXT = 200
KEEP = 1e6  # weight for summary-level evidence: dropped only after every span
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_REF_UNSAFE = re.compile(r"[^A-Za-z0-9_.\-]")
_INJECTION = re.compile(
    r"(ignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)"
    r"|disregard\s.{0,40}(instruction|rule|prompt)"
    r"|system\s+prompt|you\s+are\s+now|new\s+instructions?"
    r"|</?\s*(system|assistant|developer|telemetry_evidence|user_question)\b)",
    re.IGNORECASE,
)


class BudgetExceeded(Exception):
    """The per-investigation tool-call budget is used up."""


def ref_part(value: Any) -> str:
    return _REF_UNSAFE.sub("_", str(value))[:80]


@dataclass
class EvidenceItem:
    ref: str
    type: str  # run | span | metric | errors | comparison
    data: dict
    summary: str
    priority: int = 0  # higher = dropped first when over the context budget
    weight: float = 0.0  # tie-breaker: lower weight dropped first within a priority


@dataclass
class EvidenceBundle:
    items: dict[str, EvidenceItem] = field(default_factory=dict)
    unknown: list[str] = field(default_factory=list)
    tool_calls: int = 0
    injection_hits: int = 0
    scope_window: Optional[dict] = None
    agent_id: Optional[str] = None
    project_id: Optional[str] = None
    empty: bool = False  # no runs at all for the requested scope

    def add(self, item: EvidenceItem) -> None:
        self.items[item.ref] = item

    def note(self, text: str) -> None:
        if text not in self.unknown:
            self.unknown.append(text)

    def serialise(self) -> str:
        return json.dumps(
            [{"ref": i.ref, "type": i.type, "data": i.data} for i in self.items.values()],
            separators=(",", ":"),
        )

    def fit(self, max_chars: int) -> int:
        """Drop lowest-value items until the evidence fits ``max_chars``.

        Returns the number of omitted items. Omitted refs can no longer be cited.
        """
        omitted = 0
        while len(self.serialise()) > max_chars and len(self.items) > 1:
            victim = max(self.items.values(), key=lambda i: (i.priority, -i.weight))
            if victim.priority == 0:
                break  # never drop core evidence
            del self.items[victim.ref]
            omitted += 1
        if omitted:
            self.note(f"{omitted} lower-priority evidence item(s) were omitted to fit the context limit.")
        return omitted


class Collector:
    def __init__(
        self, tools: MonitoringTools, token: Optional[str], settings: Settings,
        project_id: Optional[str] = None,
    ) -> None:
        self.tools, self.token, self.settings, self.project_id = tools, token, settings, project_id
        self.bundle = EvidenceBundle()

    # ---- sanitising (telemetry is untrusted) -------------------------------- #
    def clean(self, value: Any, limit: int = MAX_TEXT) -> Any:
        if isinstance(value, str):
            text = _CTRL.sub(" ", value)
            if _INJECTION.search(text):
                self.bundle.injection_hits += 1
            text = text.replace("<", "&lt;").replace(">", "&gt;")
            return text[:limit]
        if isinstance(value, dict):
            return {self.clean(str(k), 64): self.clean(v, limit) for k, v in list(value.items())[:12]}
        if isinstance(value, (list, tuple)):
            return [self.clean(v, limit) for v in list(value)[:12]]
        return value

    # ---- budgeted tool access ----------------------------------------------- #
    def call(self, name: str, **kwargs: Any) -> dict:
        if self.bundle.tool_calls >= self.settings.diagnostic_max_tool_calls:
            raise BudgetExceeded()
        self.bundle.tool_calls += 1
        res = getattr(self.tools, name)(self.token, project_id=self.project_id, **kwargs)
        self.bundle.project_id = res.get("source", {}).get("project_id") or self.bundle.project_id
        return res

    def optional(self, label: str, name: str, **kwargs: Any) -> Optional[dict]:
        try:
            return self.call(name, **kwargs)
        except BudgetExceeded:
            self.bundle.note(f"{label}: not retrieved (tool-call budget reached).")
        except ToolError as exc:
            if exc.code in ("unauthorized", "insufficient_scope", "project_access_denied"):
                raise
            self.bundle.note(f"{label}: unavailable ({exc.code}).")
        return None

    # ---- evidence builders --------------------------------------------------- #
    def add_run(
        self, run: dict, priority: int, extra: Optional[dict] = None, weight: float = 0.0
    ) -> str:
        keys = (
            "run_id", "agent_id", "environment", "status", "started_at", "ended_at",
            "duration_ms", "error_type", "error_summary", "deployment_version",
            "llm_call_count", "tool_call_count", "total_tokens", "trace_id",
        )
        data = {k: self.clean(run.get(k)) for k in keys if run.get(k) is not None}
        if run.get("metadata"):  # only present when payload capture is enabled
            data["metadata"] = self.clean(run["metadata"])
        if extra:
            data.update(extra)
        ref = f"run:{ref_part(run['run_id'])}"
        dur = run.get("duration_ms")
        summary = f"run {data['run_id']} status={run.get('status')}" + (
            f", {dur} ms" if dur is not None else ""
        )
        self.bundle.add(EvidenceItem(ref, "run", data, summary, priority=priority, weight=weight))
        return ref

    def add_trace(self, run: dict, trace: dict, priority: int, label: str) -> None:
        run_id = run["run_id"]
        total = run.get("duration_ms")
        for s in trace.get("spans", []):
            dur = s.get("duration_ms")
            pct = round(100.0 * dur / total, 1) if dur is not None and total else None
            data = {
                "run_id": ref_part(run_id),
                "span_id": s["span_id"],
                "parent_span_id": s.get("parent_span_id"),
                "name": self.clean(s.get("name")),
                "event_type": s.get("event_type"),
                "status": s.get("status"),
                "start_time": s.get("start_time"),
                "duration_ms": dur,
                "pct_of_run": pct,
                "parent_missing": s.get("parent_missing"),
                "attributes": self.clean(s.get("attributes") or {}),
            }
            data = {k: v for k, v in data.items() if v is not None}
            ref = f"span:{ref_part(run_id)}:{ref_part(s['span_id'])}"
            name = data.get("name", s["span_id"])
            summary = f"span '{name}' of run {run_id} ({s.get('status')}" + (
                f", {dur} ms)" if dur is not None else ")"
            )
            self.bundle.add(
                EvidenceItem(ref, "span", data, summary, priority=priority, weight=float(dur or 0))
            )
        if not trace.get("is_complete", True):
            self.bundle.note(f"{label} trace is incomplete (no terminal event recorded).")
        if trace.get("spans_truncated"):
            self.bundle.note(f"{label} trace was truncated; not all spans are shown.")
        for msg in trace.get("unavailable", []):
            self.bundle.note(f"{label}: {self.clean(msg)}")
        missing = sum(1 for s in trace.get("spans", []) if s.get("parent_missing"))
        if missing:
            self.bundle.note(f"{label} trace has {missing} span(s) whose parent span is missing.")
        if not trace.get("spans"):
            self.bundle.note(f"{label} trace contains no spans.")

    def add_metrics(self, agent_id: str, res: dict, window_label: str) -> None:
        m = res["metrics"]
        flat: dict[str, Any] = {
            "total_runs": m["total_runs"],
            "error_rate": m["error_rate"],
            "duration_ms.avg": m["duration_ms"]["avg"],
            "duration_ms.p50": m["duration_ms"]["p50"],
            "duration_ms.p95": m["duration_ms"]["p95"],
            "duration_ms.max": m["duration_ms"]["max"],
            "llm_call_count": m["llm_call_count"],
            "tool_call_count": m["tool_call_count"],
            "total_tokens": m["total_tokens"],
        }
        for status, n in m["runs_by_status"].items():
            flat[f"runs_by_status.{status}"] = n
        for key, value in flat.items():
            if value is None:
                continue
            self.bundle.add(
                EvidenceItem(
                    f"metric:{ref_part(agent_id)}:{key}", "metric",
                    {"metric": key, "value": value, "window": res["window"], "scope": window_label},
                    f"metric {key}={value} for agent {agent_id} ({window_label})",
                    priority=1, weight=KEEP,
                )
            )
        if m.get("durations_sampled"):
            self.bundle.note("Duration percentiles were computed from a capped sample of recent runs.")
        for msg in res.get("unavailable", []):
            self.bundle.note(f"Metrics ({window_label}): {msg}")

    def add_errors(self, agent_id: str, res: dict, window_label: str) -> None:
        data = {
            "window": res["window"], "scope": window_label,
            "total_runs": res["total_runs"], "error_runs": res["error_runs"],
            "error_rate": res["error_rate"],
            "groups": [
                {"error_type": self.clean(g["error_type"]), "count": g["count"],
                 "last_seen": g["last_seen"]}
                for g in res["groups"][:10]
            ],
        }
        self.bundle.add(
            EvidenceItem(
                f"errors:{ref_part(agent_id)}", "errors", data,
                f"error summary for agent {agent_id}: {res['error_runs']}/{res['total_runs']} "
                f"runs failed ({window_label})",
                priority=1, weight=KEEP,
            )
        )

    def add_comparison(self, res: dict) -> None:
        a, b = res["run_a"]["run_id"], res["run_b"]["run_id"]
        data = {"baseline_run": ref_part(a), "target_run": ref_part(b), **res["comparison"]}
        self.bundle.add(
            EvidenceItem(
                f"comparison:{ref_part(a)}..{ref_part(b)}", "comparison", data,
                f"comparison of baseline run {a} against run {b}",
                priority=1, weight=KEEP,
            )
        )
        for msg in res.get("unavailable", []):
            self.bundle.note(f"Comparison: {msg}")

    # ---- investigations ------------------------------------------------------ #
    def collect_run(self, run_id: str) -> EvidenceBundle:
        cfg = self.settings
        details = self.call("get_run_details", run_id=run_id)  # required: errors propagate
        run = details["run"]
        self.bundle.agent_id = run["agent_id"]
        self.add_run(
            run, 0,
            {"event_type_counts": details["event_type_counts"],
             "events_truncated": details["events_truncated"]},
        )
        trace = self.optional("Target trace", "get_trace", run_id=run_id, max_spans=cfg.diagnostic_max_spans)
        if trace:
            self.add_trace(run, trace, 1, "Target run")

        started = _parse_iso(run.get("started_at"))
        if started is None:
            self.bundle.note("Run has no start time; baseline comparison unavailable.")
            return self.bundle
        after = started - timedelta(days=cfg.diagnostic_baseline_days)
        window = {"started_after": _iso(after), "started_before": _iso(started)}
        self.bundle.scope_window = window
        label = f"{cfg.diagnostic_baseline_days} days before this run"

        agent_id = run["agent_id"]
        found = self.optional(
            "Baseline lookup", "list_runs", agent_id=agent_id, status="success",
            page_size=10, **window,
        )
        baseline = pick_baseline(found["items"]) if found else None
        if baseline is None:
            if found is not None:
                self.bundle.note(f"No healthy baseline run found in the {label}.")
        else:
            self.add_run(baseline, 1, weight=KEEP)
            btrace = self.optional(
                "Baseline trace", "get_trace", run_id=baseline["run_id"],
                max_spans=min(30, cfg.diagnostic_max_spans),
            )
            if btrace:
                self.add_trace(baseline, btrace, 2, "Baseline run")
            cmp = self.optional(
                "Baseline comparison", "compare_runs",
                run_id_a=baseline["run_id"], run_id_b=run_id,
            )
            if cmp:
                self.add_comparison(cmp)
        metrics = self.optional("Agent metrics", "get_agent_metrics", agent_id=agent_id, **window)
        if metrics:
            self.add_metrics(agent_id, metrics, label)
        if run.get("status") in ("error", "unknown"):
            errs = self.optional("Error history", "get_error_summary", agent_id=agent_id, **window)
            if errs:
                self.add_errors(agent_id, errs, label)
        return self.bundle

    def collect_agent(
        self, agent_id: str, started_after: Optional[str], started_before: Optional[str]
    ) -> EvidenceBundle:
        cfg = self.settings
        self.bundle.agent_id = agent_id
        win = {"started_after": started_after, "started_before": started_before}
        metrics = self.call("get_agent_metrics", agent_id=agent_id, **win)  # required
        window = metrics["window"]
        self.bundle.scope_window = window
        label = "requested window"
        self.add_metrics(agent_id, metrics, label)
        if metrics["metrics"]["total_runs"] == 0:
            self.bundle.empty = True
            return self.bundle

        errs = self.optional("Error summary", "get_error_summary", agent_id=agent_id, **window)
        if errs:
            self.add_errors(agent_id, errs, label)

        recent = self.optional("Recent runs", "list_runs", agent_id=agent_id, page_size=20, **window)
        items = recent["items"] if recent else []
        failed = [r for r in items if r["status"] == "error"][:2]
        slow = sorted(
            (r for r in items if r.get("duration_ms") is not None and r not in failed),
            key=lambda r: r["duration_ms"], reverse=True,
        )[:2]
        anomalous = (failed + slow)[:3]
        for r in anomalous:
            self.add_run(r, 0)
        for r in anomalous:
            trace = self.optional(
                f"Trace of run {r['run_id']}", "get_trace", run_id=r["run_id"],
                max_spans=min(30, cfg.diagnostic_max_spans),
            )
            if trace:
                self.add_trace(r, trace, 1, f"Run {r['run_id']}")
        if not anomalous:
            self.bundle.note("No failed or measurably slow runs were found in the recent runs sample.")
        elif len(items) < (recent or {}).get("total", 0):
            self.bundle.note("Only the 20 most recent runs in the window were sampled for anomalies.")

        successes = [r for r in items if r["status"] == "success" and r not in anomalous]
        baseline = pick_baseline(successes)
        if baseline is None:
            self.bundle.note("No healthy baseline run found among the recent runs sample.")
        elif anomalous:
            self.add_run(baseline, 1, weight=KEEP)
            cmp = self.optional(
                "Baseline comparison", "compare_runs",
                run_id_a=baseline["run_id"], run_id_b=anomalous[0]["run_id"],
            )
            if cmp:
                self.add_comparison(cmp)
        return self.bundle


def pick_baseline(runs: list[dict]) -> Optional[dict]:
    """Pick a 'healthy' reference among successful runs.

    Heuristic: the lower-quartile duration among the sample, so a single slow
    success is not mistaken for normal behaviour. Documented in
    docs/diagnostic-assistant.md; the choice is surfaced as evidence, not hidden.
    """
    if not runs:
        return None
    timed = sorted((r for r in runs if r.get("duration_ms") is not None),
                   key=lambda r: r["duration_ms"])
    return timed[len(timed) // 4] if timed else runs[0]


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()
