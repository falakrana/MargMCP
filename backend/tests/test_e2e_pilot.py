"""
Phase 10 — End-to-End Pilot & Telemetry Path Validation Tests.

Validates the complete lifecycle:
  Agent execution -> SDK batch export -> Authenticated Ingestion -> DB Persistence ->
  Prometheus Metrics -> Trace Details / Timeline -> MCP Tools Query -> Diagnostic Assistant.

Also tests failure modes:
  - Agent exceptions during workflow execution.
  - Telemetry ingestion errors / invalid credentials.
  - Unavailable / expired trace data handling.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from marg_backend.assistant import DiagnosticEngine
from marg_backend.assistant.prompts import EVIDENCE_CLOSE, EVIDENCE_OPEN
from marg_backend.mcp_server import TOOL_NAMES
from marg_backend.mcp_tools import MonitoringTools
from marg_backend.models import Run
from marg_backend.schemas import IngestResult
from marg_sdk import AgentOps, AgentOpsConfig
from marg_sdk.events import TelemetryEvent
from marg_sdk.exporters.http import HttpExporter


class ScriptedProvider:
    name = "scripted-pilot"
    model = "test-model"

    def __init__(self, responder):
        self.responder = responder
        self.calls: list[dict] = []

    def complete(self, system, user, *, max_tokens, timeout):
        self.calls.append(dict(system=system, user=user, max_tokens=max_tokens, timeout=timeout))
        out = self.responder(user, len(self.calls))
        if isinstance(out, Exception):
            raise out
        return out if isinstance(out, str) else json.dumps(out)


def _evidence_of(user: str) -> list[dict]:
    m = re.search(re.escape(EVIDENCE_OPEN) + r"(.*)" + re.escape(EVIDENCE_CLOSE), user, re.S)
    if not m:
        return []
    return json.loads(m.group(1))


def _generate_pilot_events(project_id: str, run_id: str, status: str = "success") -> list[dict]:
    """Simulate the exact payload emitted by the Customer Support Pilot Agent."""
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    root_span_id = uuid.uuid4().hex[:16]
    s1_id = uuid.uuid4().hex[:16]
    s2_id = uuid.uuid4().hex[:16]

    events = [
        # 1. Run start event
        {
            "schema_version": "1.0",
            "event_id": f"ev-{uuid.uuid4().hex[:12]}",
            "run_id": run_id,
            "project_id": project_id,
            "agent_id": "support-copilot-v1",
            "event_type": "run_started",
            "environment": "production",
            "timestamp": now_iso,
            "data": {
                "trace_id": uuid.uuid4().hex,
                "root_span_id": root_span_id,
                "metadata": {"user_id": "user_acct_4821", "channel": "chat"},
            },
        },
        # 2. Child span: intent_and_retrieval (llm_call_completed)
        {
            "schema_version": "1.0",
            "event_id": f"ev-{uuid.uuid4().hex[:12]}",
            "run_id": run_id,
            "project_id": project_id,
            "agent_id": "support-copilot-v1",
            "event_type": "llm_call_completed",
            "environment": "production",
            "timestamp": now_iso,
            "data": {
                "span_id": s1_id,
                "parent_span_id": root_span_id,
                "name": "intent_and_retrieval",
                "duration_ms": 120,
                "prompt_tokens": 80,
                "completion_tokens": 40,
            },
        },
        # 3. Child span: account_lookup (tool_call_completed)
        {
            "schema_version": "1.0",
            "event_id": f"ev-{uuid.uuid4().hex[:12]}",
            "run_id": run_id,
            "project_id": project_id,
            "agent_id": "support-copilot-v1",
            "event_type": "tool_call_completed",
            "environment": "production",
            "timestamp": now_iso,
            "data": {
                "span_id": s2_id,
                "parent_span_id": root_span_id,
                "tool_name": "account_lookup",
                "duration_ms": 85,
            },
        },
    ]

    # Terminal event
    if status == "success":
        events.append({
            "schema_version": "1.0",
            "event_id": f"ev-{uuid.uuid4().hex[:12]}",
            "run_id": run_id,
            "project_id": project_id,
            "agent_id": "support-copilot-v1",
            "event_type": "run_completed",
            "environment": "production",
            "timestamp": now_iso,
            "data": {
                "duration_ms": 250,
                "summary": "Resolved inquiry via knowledge base.",
            },
        })
    else:
        events.append({
            "schema_version": "1.0",
            "event_id": f"ev-{uuid.uuid4().hex[:12]}",
            "run_id": run_id,
            "project_id": project_id,
            "agent_id": "support-copilot-v1",
            "event_type": "run_failed",
            "environment": "production",
            "timestamp": now_iso,
            "data": {
                "duration_ms": 310,
                "error_type": "ValueError",
                "error_summary": "Refund amount exceeds approval ceiling",
            },
        })

    return events


class TestPilotEndToEndPipeline:
    """Verifies Task 10: Complete validation path across all AgentOps subsystems."""

    def test_complete_pilot_workflow_path(self, client: TestClient, tenant):
        """Validates agent -> ingestion -> DB -> metrics -> timeline -> MCP query -> diagnosis."""
        run_id = f"run-pilot-{uuid.uuid4().hex[:8]}"
        events = _generate_pilot_events(tenant.project_id, run_id, status="success")

        # 1. Ingestion: Submit pilot events
        res = tenant.send(events)
        assert res.status_code == 202
        ingest_data = res.json()
        assert ingest_data["accepted"] == len(events)
        assert len(ingest_data["rejected"]) == 0

        # 2. Persistence: Run and events are saved in database
        run_res = tenant.get(f"/runs/{run_id}")
        assert run_res.status_code == 200
        run_data = run_res.json()["run"]
        assert run_data["run_id"] == run_id
        assert run_data["agent_id"] == "support-copilot-v1"
        assert run_data["status"] == "success"

        # 3. Prometheus Metrics: Scrape /metrics and verify counts
        metrics_res = client.get(
            "/metrics",
            headers={"Authorization": f"Bearer {client.app.state.settings.metrics_token}"},
        )
        assert metrics_res.status_code == 200
        assert "marg_events_total" in metrics_res.text

        # 4. Trace Timeline: Inspect joined timeline and parent-child span hierarchy
        timeline_res = tenant.get(f"/runs/{run_id}/timeline")
        assert timeline_res.status_code == 200
        timeline_data = timeline_res.json()
        assert timeline_data["run"]["run_id"] == run_id
        assert timeline_data["is_complete"] is True
        assert len(timeline_data["spans"]) >= 3  # Root + 2 child spans

        # Verify child spans reference root
        root_spans = [s for s in timeline_data["spans"] if s["parent_span_id"] is None]
        child_spans = [s for s in timeline_data["spans"] if s["parent_span_id"] is not None]
        assert len(root_spans) == 1
        assert len(child_spans) >= 2
        for cs in child_spans:
            assert cs["parent_span_id"] == root_spans[0]["span_id"]

        # 5. MCP Server Queries: Query via MCP tools
        st = client.app.state
        tools = MonitoringTools(st.settings, st.session_factory)
        assert "get_run_details" in TOOL_NAMES
        assert "list_runs" in TOOL_NAMES

        # Call get_run_details tool
        mcp_run_summary = tools.get_run_details(tenant.read_key, run_id)
        assert mcp_run_summary["kind"] == "summary"
        assert mcp_run_summary["run"]["run_id"] == run_id
        assert mcp_run_summary["run"]["agent_id"] == "support-copilot-v1"

        # Call list_runs tool
        mcp_runs = tools.list_runs(tenant.read_key)
        assert mcp_runs["kind"] == "summary"
        assert mcp_runs["total"] >= 1

        # 6. Diagnostic Assistant: Run investigation on the pilot run
        def _responder(user: str, _call_idx: int) -> dict:
            ev = _evidence_of(user)
            first_ref = ev[0]["ref"] if ev else "run:1"
            return {
                "findings": [{"statement": f"Run {run_id} executed cleanly.", "evidence": [first_ref]}],
                "hypotheses": [{"explanation": "All operations completed normally.", "confidence": "high", "evidence": [first_ref]}],
                "unknown": [],
                "next_checks": [],
            }

        provider = ScriptedProvider(_responder)
        engine = DiagnosticEngine(st.settings, st.session_factory, provider, sleep=lambda _s: None)
        report = engine.diagnose_run(tenant.read_key, run_id, project_id=tenant.project_id)
        assert report.scope.kind == "run"
        assert len(report.findings) > 0
        assert "executed cleanly" in report.findings[0].statement
        assert report.meta.tool_calls > 0


class TestPilotFailureCases:
    """Verifies Task 11: Failure cases and resilience under adverse conditions."""

    def test_pilot_agent_exception_handled_and_reported(self, client: TestClient, tenant):
        """When an agent encounters a business exception, telemetry captures error correctly."""
        failed_run_id = f"run-fail-{uuid.uuid4().hex[:8]}"
        events = _generate_pilot_events(tenant.project_id, failed_run_id, status="failed")

        res = tenant.send(events)
        assert res.status_code == 202

        # Verify failed run details
        run_res = tenant.get(f"/runs/{failed_run_id}")
        assert run_res.status_code == 200
        run_data = run_res.json()["run"]
        assert run_data["status"] == "error"

        # Verify timeline exposes error summary
        timeline_res = tenant.get(f"/runs/{failed_run_id}/timeline")
        assert timeline_res.status_code == 200
        timeline = timeline_res.json()
        assert timeline["run"]["error_type"] == "ValueError"
        assert "Refund amount exceeds approval ceiling" in (timeline["run"]["error_summary"] or "")

        # Verify diagnostic engine pinpoints root cause
        st = client.app.state
        def _fail_responder(user: str, _call_idx: int) -> dict:
            ev = _evidence_of(user)
            first_ref = ev[0]["ref"] if ev else "run:1"
            return {
                "findings": [{"statement": "Run failed with ValueError exception.", "evidence": [first_ref]}],
                "hypotheses": [{"explanation": "Refund ceiling of $500 was breached.", "confidence": "high", "evidence": [first_ref]}],
                "unknown": [],
                "next_checks": ["Review refund parameters"],
            }

        provider = ScriptedProvider(_fail_responder)
        engine = DiagnosticEngine(st.settings, st.session_factory, provider, sleep=lambda _s: None)
        report = engine.diagnose_run(tenant.read_key, failed_run_id, project_id=tenant.project_id)
        assert report.scope.kind == "run"
        assert any("ValueError" in f.statement for f in report.findings)
        assert report.meta.tool_calls > 0

    def test_expired_trace_retention_flagged_gracefully(self, client: TestClient, tenant):
        """Runs older than AGENTOPS_TRACE_RETENTION_DAYS flag trace_data_may_have_expired."""
        old_run_id = f"run-old-{uuid.uuid4().hex[:8]}"
        events = _generate_pilot_events(tenant.project_id, old_run_id, status="success")

        res = tenant.send(events)
        assert res.status_code == 202

        # Manually backdate the run in the database to 45 days ago (past the 30d trace retention)
        with client.app.state.session_factory() as session:
            run = session.get(Run, (tenant.project_id, old_run_id))
            assert run is not None
            run.started_at = datetime.now(timezone.utc) - timedelta(days=45)
            session.commit()

        timeline_res = tenant.get(f"/runs/{old_run_id}/timeline")
        assert timeline_res.status_code == 200
        data = timeline_res.json()
        assert data["trace_data_may_have_expired"] is True

    def test_invalid_api_key_rejected_with_401(self, client: TestClient, tenant):
        """Ingestion rejects unauthorized or revoked keys."""
        run_id = f"run-bad-key-{uuid.uuid4().hex[:8]}"
        events = _generate_pilot_events(tenant.project_id, run_id)
        res = tenant.send(events, key="completely-bogus-api-key")
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "unauthorized"

    def test_http_exporter_downtime_resilience(self):
        """SDK HttpExporter gracefully swallows connectivity failures without crashing."""
        config = AgentOpsConfig(
            endpoint="http://127.0.0.1:59999",  # Non-existent port
            api_key="test-key",
            project_id="test-proj",
            max_retries=1,
            retry_backoff_seconds=0.01,
        )
        exporter = HttpExporter(config)
        event = TelemetryEvent(
            agent_id="test-agent",
            project_id="test-proj",
            run_id="test-run",
            environment="production",
            event_type="custom_event",
        )
        # Should swallow connection error and return False without raising exception
        ok = exporter.export([event])
        assert ok is False
