"""API contract tests: documented request/response shapes, and compatibility
with the Phase 2 SDK's actual wire payload."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.conftest import Tenant, make_event


def test_openapi_documents_all_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    expected = {
        ("/v1/telemetry/events", "post"),
        ("/v1/projects/{project_id}", "get"),
        ("/v1/projects/{project_id}/agents", "get"),
        ("/v1/projects/{project_id}/agents/{agent_id}", "get"),
        ("/v1/projects/{project_id}/runs", "get"),
        ("/v1/projects/{project_id}/runs/{run_id}", "get"),
        ("/v1/projects/{project_id}/errors/summary", "get"),
        ("/v1/admin/projects", "post"),
        ("/v1/admin/projects/{project_id}/agents", "post"),
        ("/v1/admin/projects/{project_id}/api-keys", "post"),
        ("/health/live", "get"),
        ("/health/ready", "get"),
    }
    for path, method in expected:
        assert method in paths[path], (path, method)


def test_run_response_contract_fields(tenant):
    from tests.conftest import full_run

    full_run(tenant, "r")
    run = tenant.get("/runs/r").json()["run"]
    # Fields defined for the Run Record in docs/telemetry-schema.md §4.
    for field in [
        "run_id", "agent_id", "project_id", "trace_id", "root_span_id", "environment",
        "status", "started_at", "ended_at", "duration_ms", "error_type", "error_summary",
        "deployment_version", "sdk_version", "llm_call_count", "tool_call_count",
        "total_prompt_tokens", "total_completion_tokens", "total_tokens", "metadata",
        "created_at", "updated_at",
    ]:
        assert field in run, field
    assert run["status"] in {"running", "success", "error", "cancelled", "unknown"}


def test_error_envelope_contract(tenant):
    for resp in [
        tenant.get("/runs/none"),
        tenant.send([make_event("r", "run_started")], key="bad"),
        tenant.send([make_event("r", "nope")]),
        tenant.client.get("/no/such/route"),
    ]:
        body = resp.json()
        assert set(body) == {"error"}
        assert {"code", "message"} <= set(body["error"])


def test_method_not_allowed_uses_envelope(client):
    r = client.get("/v1/telemetry/events")
    assert r.status_code == 405 and r.json()["error"]["code"] == "method_not_allowed"


def test_sdk_wire_payload_is_accepted(tenant):
    """Feed the real Phase 2 SDK models through the ingestion API."""
    sdk_src = Path(__file__).resolve().parents[2] / "sdk"
    if not (sdk_src / "agentops_sdk").exists():
        pytest.skip("SDK sources not present")
    sys.path.insert(0, str(sdk_src))
    try:
        from agentops_sdk.events import EventBatchPayload, TelemetryEvent
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"SDK not importable: {exc}")
    finally:
        sys.path.remove(str(sdk_src))

    import uuid

    run_id = str(uuid.uuid4())
    base = dict(agent_id="default", project_id=tenant.project_id, run_id=run_id,
                environment="development")
    events = [
        TelemetryEvent(event_type="run_started", **base,
                       data={"trace_id": uuid.uuid4().hex, "root_span_id": uuid.uuid4().hex[:16]}),
        TelemetryEvent(event_type="output_summary", **base, data={"summary": {"ok": True}}),
        TelemetryEvent(event_type="run_completed", **base),
    ]
    payload = EventBatchPayload(project_id=tenant.project_id, batch=events).model_dump()
    r = tenant.client.post("/v1/telemetry/events", json=payload,
                           headers={"Authorization": f"Bearer {tenant.ingest_key}"})
    assert r.status_code == 202, r.text
    assert r.json()["accepted"] == 3 and r.json()["rejected"] == []
    assert tenant.get(f"/runs/{run_id}").json()["run"]["status"] == "success"
