"""Bounded diagnostic investigation workflow.

scope -> retrieve evidence (authorised read-only tools, budgeted) -> sanitise &
fit context -> one LLM call (timeout, token cap, bounded retries) -> parse ->
verify every citation against the retrieved evidence -> report.

The LLM is never the source of truth: statements without a citation that
resolves to retrieved evidence are dropped, and the evidence list in the report
is built from retrieved records, not from model text.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from marg_backend.assistant.evidence import Collector, EvidenceBundle, BudgetExceeded
from marg_backend.assistant.models import (
    DiagnosticMeta,
    DiagnosticReport,
    EvidenceRef,
    Finding,
    Hypothesis,
    Scope,
)
from marg_backend.assistant.prompts import SYSTEM_PROMPT, build_user_message
from marg_backend.assistant.providers import LLMProvider, ProviderError
from marg_backend.config import Settings
from marg_backend.errors import ApiError
from marg_backend.mcp_tools import MonitoringTools, ToolError

logger = logging.getLogger("marg_backend.assistant")

MAX_QUESTION_CHARS = 500
MAX_ITEMS = 10
MAX_STATEMENT_CHARS = 500

_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
# The assistant has no write capability; any claim that it took an action is
# false by construction and is removed from the report.
_ACTION_CLAIM = re.compile(
    r"\b(i|we|the assistant)\s+(have\s+|has\s+|'ve\s+|already\s+|successfully\s+|just\s+)*"
    r"(restarted|rebooted|fixed|applied|deployed|rolled\s+back|executed|ran|run|modified|"
    r"updated|deleted|patched|remediated|changed|scaled|resolved|reconfigured|redeployed)\b"
    r"|\b(has|have)\s+been\s+(automatically\s+)?"
    r"(restarted|fixed|patched|remediated|rolled\s+back|redeployed|reconfigured)\b",
    re.IGNORECASE,
)

_ERROR_STATUS = {
    "unauthorized": 401, "insufficient_scope": 403, "project_access_denied": 403,
    "forbidden": 403, "not_found": 404, "invalid_argument": 422,
    "invalid_time_range": 422, "time_range_too_large": 422,
    "storage_unavailable": 503,
}
_PROVIDER_ERRORS = {
    "timeout": (504, "assistant_timeout", "The language model timed out."),
    "rate_limited": (429, "assistant_rate_limited", "The language model is rate limiting requests."),
    "unavailable": (502, "assistant_provider_error", "The language model provider is unavailable."),
    "auth": (502, "assistant_provider_error", "The language model provider rejected the configured credentials."),
    "invalid_response": (502, "assistant_invalid_response", "The language model returned an unusable response."),
}
_RETRYABLE = {"rate_limited", "unavailable", "invalid_response"}


def _api_error_from_tool(exc: ToolError) -> ApiError:
    return ApiError(_ERROR_STATUS.get(exc.code, 500), exc.code, exc.message)


def _clip(value: Any, limit: int = MAX_STATEMENT_CHARS) -> str:
    return _CTRL.sub(" ", str(value)).strip()[:limit]


def _extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no json object")
    obj = json.loads(text[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError("not an object")
    return obj


class DiagnosticEngine:
    def __init__(
        self,
        settings: Settings,
        session_factory: Callable[[], Session],
        provider: Optional[LLMProvider],
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.tools = MonitoringTools(settings, session_factory)
        self._sleep = sleep

    # ------------------------------ public API ------------------------------ #
    def diagnose_run(
        self, token: Optional[str], run_id: str, *, project_id: Optional[str] = None,
        question: Optional[str] = None,
    ) -> DiagnosticReport:
        return self._investigate(
            "run", token, project_id, question,
            lambda c: c.collect_run(run_id),
            lambda b, pid: Scope(kind="run", project_id=pid, run_id=run_id, agent_id=b.agent_id,
                                 **(b.scope_window or {})),
            f"investigate run '{run_id}'",
        )

    def diagnose_agent(
        self, token: Optional[str], agent_id: str, *, project_id: Optional[str] = None,
        started_after: Optional[str] = None, started_before: Optional[str] = None,
        question: Optional[str] = None,
    ) -> DiagnosticReport:
        return self._investigate(
            "agent", token, project_id, question,
            lambda c: c.collect_agent(agent_id, started_after, started_before),
            lambda b, pid: Scope(kind="agent", project_id=pid, agent_id=agent_id,
                                 **(b.scope_window or {})),
            f"investigate agent '{agent_id}' over the requested window",
        )

    # ------------------------------ internals ------------------------------- #
    def _investigate(self, kind, token, project_id, question, collect, make_scope, scope_text):
        started = time.monotonic()
        if self.provider is None:
            raise ApiError(
                503, "assistant_not_configured",
                "The diagnostic assistant is not configured on this server.",
            )
        if question is not None:
            question = _clip(question, MAX_QUESTION_CHARS)
            if not question:
                question = None

        collector = Collector(self.tools, token, self.settings, project_id)
        outcome = "ok"
        llm_calls = 0
        try:
            try:
                bundle = collect(collector)
            except ToolError as exc:
                outcome = exc.code
                raise _api_error_from_tool(exc) from None
            except BudgetExceeded:
                outcome = "budget_exceeded"
                raise ApiError(
                    422, "tool_budget_exceeded", "Evidence retrieval budget is too small."
                ) from None

            # Project of the authenticated key (resolved by the tool layer).
            scope = make_scope(bundle, bundle.project_id or "")
            scope.question = question and collector.clean(question, MAX_QUESTION_CHARS)

            if bundle.empty:
                outcome = "no_evidence"
                return self._no_evidence_report(scope, bundle, started)

            bundle.fit(self.settings.diagnostic_max_context_chars)
            user = build_user_message(
                scope_text, scope.question, bundle.serialise()
            )
            raw, llm_calls = self._ask(user)
            try:
                parsed = _extract_json(raw)
            except ValueError:
                outcome = "invalid_response"
                raise ApiError(502, "assistant_invalid_response",
                               "The language model returned an unusable response.") from None
            report = self._verify(parsed, scope, bundle, started, llm_calls)
            return report
        except ApiError as exc:
            if outcome == "ok":
                outcome = exc.code
            raise
        finally:
            logger.info(
                "diagnostic scope=%s outcome=%s tool_calls=%d llm_calls=%d duration_ms=%d",
                kind, outcome, collector.bundle.tool_calls, llm_calls,
                int((time.monotonic() - started) * 1000),
            )

    def _ask(self, user: str) -> tuple[str, int]:
        cfg = self.settings
        attempts = 1 + cfg.diagnostic_llm_max_retries
        calls = 0
        for attempt in range(attempts):
            calls += 1
            try:
                text = self.provider.complete(  # type: ignore[union-attr]
                    SYSTEM_PROMPT, user,
                    max_tokens=cfg.diagnostic_llm_max_tokens,
                    timeout=float(cfg.diagnostic_timeout_seconds),
                )
                if "{" not in text:
                    raise ProviderError("invalid_response")
                return text, calls
            except ProviderError as exc:
                if exc.kind in _RETRYABLE and attempt + 1 < attempts:
                    self._sleep(min(2.0 * (attempt + 1), 5.0))
                    continue
                status, code, message = _PROVIDER_ERRORS.get(
                    exc.kind, _PROVIDER_ERRORS["unavailable"]
                )
                raise ApiError(status, code, message) from None
        raise ApiError(502, "assistant_provider_error", "The language model provider is unavailable.")

    def _no_evidence_report(self, scope: Scope, bundle: EvidenceBundle, started: float) -> DiagnosticReport:
        return DiagnosticReport(
            scope=scope,
            unknown=[
                "No runs were recorded for this agent in the requested window, so there is "
                "nothing to diagnose. No language model was consulted.",
                *bundle.unknown,
            ],
            next_checks=[
                "Confirm the agent is instrumented and sending telemetry (check the SDK configuration).",
                "Widen the time window or check the agent identifier.",
            ],
            meta=self._meta(bundle, started, 0, skipped=True),
        )

    def _meta(self, bundle, started, llm_calls, *, skipped=False, **counters) -> DiagnosticMeta:
        return DiagnosticMeta(
            provider=self.provider.name if self.provider else None,
            model=self.provider.model if self.provider else None,
            tool_calls=bundle.tool_calls,
            llm_calls=llm_calls,
            duration_ms=int((time.monotonic() - started) * 1000),
            generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            evidence_items=len(bundle.items),
            llm_skipped=skipped,
            suspicious_content_detected=bundle.injection_hits,
            **counters,
        )

    # ---------------------- verification of model output ---------------------- #
    def _verify(self, parsed: dict, scope: Scope, bundle: EvidenceBundle,
                started: float, llm_calls: int) -> DiagnosticReport:
        valid = bundle.items
        dropped = rejected = blocked = 0

        def refs_of(entry: dict) -> list[str]:
            nonlocal rejected
            raw = entry.get("evidence")
            out: list[str] = []
            for r in raw if isinstance(raw, list) else []:
                if isinstance(r, str) and r in valid:
                    if r not in out:
                        out.append(r)
                else:
                    rejected += 1
            return out

        def clean_text(value: Any) -> Optional[str]:
            nonlocal blocked
            text = _clip(value)
            if not text:
                return None
            if _ACTION_CLAIM.search(text):
                blocked += 1
                return None
            return text

        findings: list[Finding] = []
        for entry in _dicts(parsed.get("findings")):
            text, refs = clean_text(entry.get("statement")), refs_of(entry)
            if text is None:
                continue
            if not refs:
                dropped += 1
                continue
            findings.append(Finding(statement=text, evidence=refs))

        hypotheses: list[Hypothesis] = []
        for entry in _dicts(parsed.get("hypotheses")):
            text, refs = clean_text(entry.get("explanation")), refs_of(entry)
            if text is None:
                continue
            if not refs:
                dropped += 1
                continue
            conf = str(entry.get("confidence", "")).lower()
            hypotheses.append(Hypothesis(
                explanation=text,
                confidence=conf if conf in ("high", "medium", "low") else "low",
                evidence=refs,
                uncertainty=_clip(entry.get("uncertainty", "")),
            ))

        unknown = list(bundle.unknown)
        for item in _strings(parsed.get("unknown")):
            t = clean_text(item)
            if t and t not in unknown:
                unknown.append(t)
        next_checks = [t for t in (clean_text(s) for s in _strings(parsed.get("next_checks"))) if t]

        if not findings and not hypotheses:
            unknown.append(
                "The model produced no statements that could be tied to retrieved evidence."
            )

        cited: list[str] = []
        for r in [r for f in findings[:MAX_ITEMS] for r in f.evidence] + \
                [r for h in hypotheses[:MAX_ITEMS] for r in h.evidence]:
            if r not in cited:
                cited.append(r)
        evidence = [
            EvidenceRef(ref=r, type=valid[r].type, summary=valid[r].summary) for r in cited
        ]
        return DiagnosticReport(
            scope=scope,
            findings=findings[:MAX_ITEMS],
            likely_explanations=hypotheses[:MAX_ITEMS],
            evidence=evidence,
            unknown=unknown[: MAX_ITEMS * 3],
            next_checks=next_checks[:MAX_ITEMS],
            meta=self._meta(
                bundle, started, llm_calls,
                dropped_uncited_statements=dropped, rejected_citations=rejected,
                blocked_action_claims=blocked,
            ),
        )


def _dicts(value: Any) -> list[dict]:
    return [v for v in value if isinstance(v, dict)][:MAX_ITEMS] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [v for v in value if isinstance(v, str)][:MAX_ITEMS] if isinstance(value, list) else []
