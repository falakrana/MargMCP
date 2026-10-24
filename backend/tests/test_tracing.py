"""Phase 4 — OpenTelemetry tracing: span content, correlation, sampling, resilience."""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from prometheus_client.parser import text_string_to_metric_families

from marg_backend.main import create_app
from tests.conftest import Tenant, full_run, make_event, make_settings

ALLOWED_SPAN_ATTRS = {
    "marg.project_id", "marg.agent_id", "marg.run_id", "marg.environment",
    "marg.run_status", "marg.batch_size", "marg.accepted", "marg.duplicates",
    "marg.rejected", "llm.provider", "llm.model", "llm.prompt_tokens",
    "llm.completion_tokens", "llm.total_tokens", "tool.name", "tool.type", "error.type",
}
FORBIDDEN_FRAGMENTS = ("prompt\"", "response", "tool.input", "tool.output", "secret", "password")


def hex_id(value: int, width: int) -> str:
    return format(value, f"0{width}x")


class Harness:
    def __init__(self, client: TestClient, exporter, app):
        self.client, self.exporter, self.app = client, exporter, app
        self.tenant = Tenant(client)

    def flush(self):
        assert self.app.state.observability.tracing.force_flush(10000)

    def spans(self):
        self.flush()
        return list(self.exporter.get_finished_spans())

    def metric(self, name, **labels):
        total = 0.0
        text = self.client.get("/metrics").text
        for fam in text_string_to_metric_families(text):
            for s in fam.samples:
                if s.name == name and all(s.labels.get(k) == v for k, v in labels.items()):
                    total += s.value
        return total


def build(db_path, exporter=None, **overrides):
    exporter = exporter or InMemorySpanExporter()
    app = create_app(make_settings(db_path, **overrides), span_exporter=exporter)
    client = TestClient(app, raise_server_exceptions=False)
    client.__enter__()
    return Harness(client, exporter, app)


@pytest.fixture
def traced(db_path):
    h = build(db_path)
    yield h
    h.client.__exit__(None, None, None)


# ------------------------------- content ---------------------------------- #
def test_run_exports_root_and_child_spans_correlated_to_run(traced):
    full_run(traced.tenant, "run-1", duration=2)
    spans = traced.spans()
    run = traced.tenant.get("/runs/run-1").json()["run"]

    roots = [s for s in spans if s.name == "agent.run"]
    assert len(roots) == 1
    root = roots[0]
    # Trace/run correlation: ids on the span equal the ids stored on the run.
    assert hex_id(root.context.trace_id, 32) == run["trace_id"]
    assert hex_id(root.context.span_id, 16) == run["root_span_id"]
    assert root.attributes["marg.run_id"] == "run-1"
    assert root.attributes["marg.agent_id"] == "agent-1"
    assert root.status.status_code == StatusCode.OK
    assert (root.end_time - root.start_time) / 1e9 == pytest.approx(2.0, abs=0.01)
    assert root.parent is None

    children = [s for s in spans if s.name in ("llm.chat", "tool.call")]
    assert {c.name for c in children} == {"llm.chat", "tool.call"} or len(children) == 2
    for child in children:
        assert hex_id(child.context.trace_id, 32) == run["trace_id"]
        assert hex_id(child.parent.span_id, 16) == run["root_span_id"]
        assert child.attributes["marg.run_id"] == "run-1"
    llm = next(s for s in spans if s.name == "llm.chat")
    assert llm.attributes["llm.prompt_tokens"] == "10"


def test_failed_run_root_span_has_error_status(traced):
    full_run(traced.tenant, "run-err", fail=True)
    root = next(s for s in traced.spans() if s.name == "agent.run")
    assert root.status.status_code == StatusCode.ERROR
    assert root.attributes["error.type"] == "TimeoutError"
    assert root.attributes["marg.run_status"] == "error"


def test_failed_llm_call_span_is_error(traced):
    traced.tenant.send([
        make_event("r", "run_started"),
        make_event("r", "llm_call_failed", data={"provider": "openai", "model": "gpt-4o",
                                                  "duration_ms": 2000}),
    ])
    span = next(s for s in traced.spans() if s.name == "llm.chat")
    assert span.status.status_code == StatusCode.ERROR
    assert (span.end_time - span.start_time) / 1e9 == pytest.approx(2.0, abs=0.01)


def test_ingestion_request_gets_a_live_span(traced):
    full_run(traced.tenant, "run-req")
    span = next(s for s in traced.spans() if s.name == "ingest.batch")
    assert span.attributes["marg.accepted"] == 4
    assert span.attributes["marg.batch_size"] == 4
    assert span.attributes["marg.project_id"] == traced.tenant.project_id


def test_out_of_order_start_still_exports_root_with_correct_ids(traced):
    from datetime import timedelta
    from tests.conftest import now
    start = now() - timedelta(minutes=1)
    traced.tenant.send([make_event("o", "run_completed", start + timedelta(seconds=3))])
    assert not [s for s in traced.spans() if s.name == "agent.run"]  # start unknown yet
    traced.tenant.send([make_event("o", "run_started", start)])
    root = next(s for s in traced.spans() if s.name == "agent.run")
    run = traced.tenant.get("/runs/o").json()["run"]
    assert hex_id(root.context.trace_id, 32) == run["trace_id"]
    assert (root.end_time - root.start_time) / 1e9 == pytest.approx(3.0, abs=0.01)


def test_duplicates_do_not_export_duplicate_spans(traced):
    events = [make_event("d", "run_started"), make_event("d", "llm_call_completed"),
              make_event("d", "run_completed")]
    traced.tenant.send(events)
    traced.tenant.send(events)
    spans = traced.spans()
    assert len([s for s in spans if s.name == "agent.run"]) == 1
    assert len([s for s in spans if s.name == "llm.chat"]) == 1


def test_span_attributes_exclude_sensitive_data(traced):
    traced.tenant.send([
        make_event("s", "run_started", data={"metadata": {"note": "customer says hello"}}),
        make_event("s", "llm_call_completed", data={"provider": "p", "model": "m",
                                                     "prompt_tokens": 1, "completion_tokens": 1}),
        make_event("s", "run_failed", data={"error_type": "Boom",
                                            "error_summary": "password=hunter2"}),
    ])
    for span in traced.spans():
        assert set(span.attributes) <= ALLOWED_SPAN_ATTRS, set(span.attributes) - ALLOWED_SPAN_ATTRS
        blob = str(dict(span.attributes)) + span.name
        assert "hunter2" not in blob and "customer says hello" not in blob
        assert not any(f in blob for f in FORBIDDEN_FRAGMENTS)


# ------------------------------- sampling ---------------------------------- #
def test_error_traces_are_not_sampled_away(db_path):
    h = build(db_path, trace_sample_ratio=0.0)
    try:
        full_run(h.tenant, "ok-run")
        full_run(h.tenant, "bad-run", fail=True)
        spans = h.spans()
        names = [(s.name, s.attributes.get("marg.run_id")) for s in spans]
        assert ("agent.run", "bad-run") in names          # error root always exported
        assert ("agent.run", "ok-run") not in names        # healthy run sampled out
        assert h.metric("marg_trace_spans_total", outcome="sampled_out") >= 1
    finally:
        h.client.__exit__(None, None, None)


def test_ratio_one_exports_everything(db_path):
    h = build(db_path, trace_sample_ratio=1.0)
    try:
        full_run(h.tenant, "ok-run")
        assert any(s.name == "agent.run" for s in h.spans())
    finally:
        h.client.__exit__(None, None, None)


# ----------------------------- resilience ---------------------------------- #
class ExplodingExporter(SpanExporter):
    def __init__(self):
        self.calls = 0

    def export(self, spans):
        self.calls += 1
        raise ConnectionError("trace backend is down")

    def shutdown(self):
        pass


def test_exporter_failure_is_observable_and_never_breaks_ingestion(db_path):
    exporter = ExplodingExporter()
    h = build(db_path, exporter=exporter)
    try:
        for i in range(3):
            r = h.tenant.send([make_event(f"r{i}", "run_started"),
                               make_event(f"r{i}", "run_completed")])
            assert r.status_code == 202 and r.json()["accepted"] == 2
        h.flush()
        assert exporter.calls >= 1
        assert h.metric("marg_trace_export_failures_total") >= 1
        assert h.client.get("/health/ready").status_code == 200
        assert h.tenant.get("/runs/r0").json()["run"]["status"] == "success"
    finally:
        h.client.__exit__(None, None, None)


class FailureResultExporter(SpanExporter):
    def export(self, spans):
        return SpanExportResult.FAILURE

    def shutdown(self):
        pass


def test_failure_result_is_counted(db_path):
    h = build(db_path, exporter=FailureResultExporter())
    try:
        full_run(h.tenant, "x")
        h.flush()
        assert h.metric("marg_trace_export_failures_total") >= 1
    finally:
        h.client.__exit__(None, None, None)


def test_tracing_is_disabled_without_endpoint_or_exporter(db_path):
    app = create_app(make_settings(db_path))
    with TestClient(app, raise_server_exceptions=False) as client:
        assert app.state.observability.tracing.enabled is False
        t = Tenant(client)
        full_run(t, "no-trace")
        assert t.get("/runs/no-trace").json()["run"]["status"] == "success"


def test_unreachable_otlp_endpoint_does_not_break_the_backend(db_path):
    # Port 9 (discard) on localhost: nothing is listening.
    h = None
    app = create_app(make_settings(db_path, otlp_endpoint="http://127.0.0.1:9/v1/traces",
                                   trace_export_timeout_seconds=1))
    with TestClient(app, raise_server_exceptions=False) as client:
        t = Tenant(client)
        r = t.send([make_event("u", "run_started"), make_event("u", "run_completed")])
        assert r.status_code == 202
        assert app.state.observability.tracing.enabled is True
        app.state.observability.tracing.force_flush(15000)
        assert client.get("/health/ready").status_code == 200
        text = client.get("/metrics").text
        failures = sum(
            s.value for fam in text_string_to_metric_families(text) for s in fam.samples
            if s.name == "marg_trace_export_failures_total"
        )
        assert failures >= 1
        assert t.get("/runs/u").json()["run"]["status"] == "success"


# ----------------------- real OTLP/HTTP wire export ------------------------ #
class _Receiver(BaseHTTPRequestHandler):
    bodies: list[bytes] = []
    paths: list[str] = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        _Receiver.bodies.append(self.rfile.read(length))
        _Receiver.paths.append(self.path)
        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.end_headers()

    def log_message(self, *args):  # silence
        pass


def test_spans_are_exported_over_real_otlp_http(db_path):
    """Uses the real OTLP/HTTP exporter against a local receiver (not Tempo)."""
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

    _Receiver.bodies, _Receiver.paths = [], []
    server = HTTPServer(("127.0.0.1", 0), _Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_address[1]}/v1/traces"
        app = create_app(make_settings(db_path, otlp_endpoint=endpoint))
        with TestClient(app, raise_server_exceptions=False) as client:
            t = Tenant(client)
            full_run(t, "wire-run", fail=True)
            assert app.state.observability.tracing.force_flush(15000)
            run = t.get("/runs/wire-run").json()["run"]
        assert _Receiver.paths and set(_Receiver.paths) == {"/v1/traces"}
        found = {}
        for body in _Receiver.bodies:
            req = ExportTraceServiceRequest()
            req.ParseFromString(body)
            for rs in req.resource_spans:
                res = {a.key: a.value.string_value for a in rs.resource.attributes}
                assert res["service.name"] == "marg-backend"
                for ss in rs.scope_spans:
                    for sp in ss.spans:
                        found[sp.name] = sp
        root = found["agent.run"]
        assert root.trace_id.hex() == run["trace_id"]
        assert root.span_id.hex() == run["root_span_id"]
        assert root.status.code == 2  # STATUS_CODE_ERROR
        assert found["llm.chat"].parent_span_id.hex() == run["root_span_id"]
    finally:
        server.shutdown()
        server.server_close()
