"""Phase 4 — Prometheus metrics: names/types, lifecycle counters, label safety, auth."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families

from agentops_backend.main import create_app
from agentops_backend.metrics import BoundedLabel, Metrics
from agentops_backend.observability import Observability
from tests.conftest import Tenant, bearer, full_run, make_event, make_settings, now

METRICS_TOKEN = "metrics-secret-token-for-tests"

ALLOWED_LABELS = {
    "agent_id", "environment", "status", "provider", "model", "tool_name",
    "token_type", "endpoint", "outcome", "code", "version", "scope",
}
FORBIDDEN_LABELS = {
    "run_id", "event_id", "trace_id", "span_id", "user_id", "project_id",
    "prompt", "response", "error_message", "error_summary", "exception",
}


def scrape(client: TestClient, headers=None) -> str:
    r = client.get("/metrics", headers=headers or {})
    assert r.status_code == 200, r.text
    return r.text


def sample(client: TestClient, name: str, **labels) -> float:
    """Sum of all samples called ``name`` whose labels include ``labels``."""
    total = 0.0
    for family in text_string_to_metric_families(scrape(client)):
        for s in family.samples:
            if s.name == name and all(s.labels.get(k) == v for k, v in labels.items()):
                total += s.value
    return total


# ----------------------------- definitions -------------------------------- #
def test_expected_metric_names_and_types():
    metrics = Metrics()
    types = {}
    for family in metrics.registry.collect():
        types[family.name] = family.type
    assert types["agentops_runs"] == "counter"
    assert types["agentops_run_duration_seconds"] == "histogram"
    assert types["agentops_llm_calls"] == "counter"
    assert types["agentops_llm_call_duration_seconds"] == "histogram"
    assert types["agentops_tool_calls"] == "counter"
    assert types["agentops_tool_call_duration_seconds"] == "histogram"
    assert types["agentops_tokens"] == "counter"
    assert types["agentops_ingestion_requests"] == "counter"
    assert types["agentops_ingestion_latency_seconds"] == "histogram"
    assert types["agentops_events"] == "counter"
    assert types["agentops_trace_export_failures"] == "counter"


def test_all_metric_label_names_are_bounded_and_private():
    metrics = Metrics()
    names: set[str] = set()
    for collector in set(metrics.registry._names_to_collectors.values()):
        names.update(getattr(collector, "_labelnames", ()))
    assert names, "expected labelled metrics"
    assert names <= ALLOWED_LABELS, f"unexpected labels: {names - ALLOWED_LABELS}"
    assert not (names & FORBIDDEN_LABELS)


def test_bounded_label_sanitises_and_caps_cardinality():
    label = BoundedLabel(max_values=3, max_len=10)
    assert label("a b\nc") == "a_b_c"
    assert label("x" * 50) == "x" * 10
    assert label(None) == "unknown" and label("   ") == "unknown"
    label("one")  # third distinct value
    assert label("brand-new") == BoundedLabel.OVERFLOW
    assert label("one") == "one"  # previously seen values stay stable


# ------------------------------ lifecycle --------------------------------- #
def test_counters_reflect_a_successful_run(client, tenant):
    full_run(tenant, "run-ok", duration=2)
    assert sample(client, "agentops_runs_total", agent_id="agent-1",
                  environment="production", status="success") == 1
    assert sample(client, "agentops_run_duration_seconds_count", agent_id="agent-1") == 1
    assert sample(client, "agentops_run_duration_seconds_sum", agent_id="agent-1") == pytest.approx(2.0)
    assert sample(client, "agentops_llm_calls_total", status="ok") == 1
    assert sample(client, "agentops_tool_calls_total", status="ok") == 1
    assert sample(client, "agentops_tokens_total", token_type="prompt") == 10
    assert sample(client, "agentops_tokens_total", token_type="completion") == 5
    assert sample(client, "agentops_events_total", outcome="accepted") == 4
    assert sample(client, "agentops_ingestion_requests_total", status="202",
                  endpoint="/v1/telemetry/events") == 1
    assert sample(client, "agentops_ingestion_latency_seconds_count",
                  endpoint="/v1/telemetry/events") == 1


def test_failed_run_counts_as_error(client, tenant):
    full_run(tenant, "run-bad", fail=True)
    assert sample(client, "agentops_runs_total", status="error") == 1
    assert sample(client, "agentops_runs_total", status="success") == 0


def test_llm_and_tool_failures_and_reported_durations(client, tenant):
    events = [
        make_event("r", "run_started"),
        make_event("r", "llm_call_failed", data={
            "provider": "openai", "model": "gpt-4o", "duration_ms": 1500}),
        make_event("r", "tool_call_failed", data={"tool_name": "search", "duration_ms": 250}),
        make_event("r", "run_failed", data={"error_type": "ToolError"}),
    ]
    assert tenant.send(events).status_code == 202
    assert sample(client, "agentops_llm_calls_total", provider="openai",
                  model="gpt-4o", status="error") == 1
    assert sample(client, "agentops_llm_call_duration_seconds_sum",
                  provider="openai") == pytest.approx(1.5)
    assert sample(client, "agentops_tool_calls_total", tool_name="search", status="error") == 1
    assert sample(client, "agentops_tool_call_duration_seconds_sum",
                  tool_name="search") == pytest.approx(0.25)
    # failed LLM calls do not add tokens
    assert sample(client, "agentops_tokens_total") == 0


def test_duplicate_retries_do_not_double_count(client, tenant):
    events = [
        make_event("dup", "run_started"),
        make_event("dup", "llm_call_completed", data={"prompt_tokens": 7, "completion_tokens": 3}),
        make_event("dup", "run_completed"),
    ]
    assert tenant.send(events).json()["accepted"] == 3
    assert tenant.send(events).json()["duplicates"] == 3
    assert sample(client, "agentops_runs_total") == 1
    assert sample(client, "agentops_tokens_total", token_type="prompt") == 7
    assert sample(client, "agentops_events_total", outcome="accepted") == 3
    assert sample(client, "agentops_events_total", outcome="duplicate") == 3
    assert sample(client, "agentops_run_duration_seconds_count") == 1


def test_rejected_events_are_counted_by_code(client, tenant):
    bad = make_event("rej", "run_started", data={"prompt": "secret user text"})
    r = tenant.send([bad])
    assert r.json()["rejected"][0]["code"] == "forbidden_attribute"
    assert sample(client, "agentops_events_total", outcome="rejected") == 1
    assert sample(client, "agentops_events_rejected_total", code="forbidden_attribute") == 1
    assert "secret user text" not in scrape(client)


def test_repeat_of_same_terminal_status_is_not_a_new_run_result(client, tenant):
    start = now() - timedelta(minutes=1)
    tenant.send([make_event("t", "run_started", start),
                 make_event("t", "run_completed", start + timedelta(seconds=1))])
    again = tenant.send([make_event("t", "run_completed", start + timedelta(seconds=1))])
    assert again.json()["accepted"] == 1  # new event id, accepted but a no-op
    assert sample(client, "agentops_runs_total", status="success") == 1
    assert sample(client, "agentops_run_duration_seconds_count") == 1


def test_out_of_order_terminal_before_start_counts_once(client, tenant):
    start = now() - timedelta(minutes=1)
    tenant.send([make_event("ooo", "run_completed", start + timedelta(seconds=2))])
    assert sample(client, "agentops_runs_total", status="success") == 1
    assert sample(client, "agentops_run_duration_seconds_count") == 0  # start unknown yet
    tenant.send([make_event("ooo", "run_started", start)])
    assert sample(client, "agentops_runs_total", status="success") == 1
    assert sample(client, "agentops_run_duration_seconds_count") == 1
    assert sample(client, "agentops_run_duration_seconds_sum") == pytest.approx(2.0)


def test_ingestion_request_metrics_cover_auth_failures(client, tenant):
    r = client.post("/v1/telemetry/events", json={}, headers=bearer("aop_deadbeef_nope"))
    assert r.status_code == 401
    assert sample(client, "agentops_ingestion_requests_total", status="401") == 1


# ------------------------- cardinality & privacy -------------------------- #
def test_model_label_cardinality_is_capped(client, tenant):
    events = []
    for i in range(150):
        events.append(make_event("card", "llm_call_completed",
                                 data={"provider": "p", "model": f"model-{i}",
                                       "prompt_tokens": 1, "completion_tokens": 1}))
    for i in range(0, 150, 50):
        assert tenant.send(events[i:i + 50]).status_code == 202
    models = set()
    for family in text_string_to_metric_families(scrape(client)):
        for s in family.samples:
            if s.name == "agentops_llm_calls_total":
                models.add(s.labels["model"])
    assert len(models) <= 101 and "other" in models


def test_metrics_never_expose_ids_or_free_text(client, tenant):
    run_id = f"run-{uuid.uuid4()}"
    trace = uuid.uuid4().hex
    events = [
        make_event(run_id, "run_started", data={"trace_id": trace, "root_span_id": trace[:16],
                                                  "metadata": {"note": "customer says hello"}}),
        make_event(run_id, "llm_call_completed",
                   data={"provider": "my provider\nwith newline", "model": "m",
                         "prompt_tokens": 1, "completion_tokens": 1}),
        make_event(run_id, "run_failed",
                   data={"error_type": "Boom", "error_summary": "password=hunter2"}),
    ]
    assert tenant.send(events).status_code == 202
    text = scrape(client)
    for secret in (run_id, trace, trace[:16], "customer says hello", "hunter2", tenant.project_id):
        assert secret not in text
    assert 'provider="my_provider_with_newline"' in text


# --------------------------- /metrics boundary ----------------------------- #
def _app(db_path, **overrides):
    return TestClient(create_app(make_settings(db_path, **overrides)),
                      raise_server_exceptions=False)


def test_metrics_open_in_development_without_token(client):
    assert client.get("/metrics").status_code == 200
    assert "agentops_backend_info" in scrape(client)


def test_metrics_require_bearer_token_when_configured(db_path):
    with _app(db_path, metrics_token=METRICS_TOKEN) as c:
        assert c.get("/metrics").status_code == 401
        assert c.get("/metrics", headers=bearer("wrong")).status_code == 401
        assert c.get("/metrics", headers=bearer(METRICS_TOKEN)).status_code == 200
        body = c.get("/metrics").json()
        assert body["error"]["code"] == "unauthorized"


def test_metrics_disabled_outside_development_without_token(db_path):
    with _app(db_path, env="production") as c:
        r = c.get("/metrics")
        assert r.status_code == 503 and r.json()["error"]["code"] == "metrics_disabled"
    with _app(db_path, env="production", metrics_token=METRICS_TOKEN) as c:
        assert c.get("/metrics", headers=bearer(METRICS_TOKEN)).status_code == 200


def test_ingest_and_query_keys_cannot_scrape_metrics(db_path):
    with _app(db_path, metrics_token=METRICS_TOKEN) as c:
        t = Tenant(c)
        assert c.get("/metrics", headers=bearer(t.full_key)).status_code == 401


# ------------------------------ fault isolation ---------------------------- #
def test_metric_recording_errors_never_break_ingestion(client, tenant, monkeypatch):
    def boom(self, obs):
        raise RuntimeError("metrics backend exploded")

    monkeypatch.setattr(Observability, "_record_event", boom)
    r = tenant.send([make_event("iso", "run_started"), make_event("iso", "run_completed")])
    assert r.status_code == 202 and r.json()["accepted"] == 2
    assert tenant.get("/runs/iso").json()["run"]["status"] == "success"  # data still stored
    assert sample(client, "agentops_observability_errors_total") == 2
