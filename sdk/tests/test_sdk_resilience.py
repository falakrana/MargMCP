"""Phase 9 — SDK resilience, bounded retries, jitter, outage handling, and queue bounds."""
import time
import pytest
import responses
import requests

from agentops_sdk import AgentOps, AgentOpsConfig
from agentops_sdk.events import TelemetryEvent
from agentops_sdk.exporters.http import HttpExporter
from agentops_sdk.redaction import redact_sensitive_data


def test_http_exporter_retries_transient_503_and_succeeds():
    config = AgentOpsConfig(
        api_endpoint="http://testserver",
        project_id="test-p",
        max_retries=2,
        retry_backoff_seconds=0.01,  # fast backoff for tests
    )
    exporter = HttpExporter(config)

    with responses.RequestsMock() as rsps:
        # 1st attempt: 503, 2nd attempt: 202
        rsps.add(responses.POST, "http://testserver/v1/telemetry/events", status=503)
        rsps.add(responses.POST, "http://testserver/v1/telemetry/events", status=202)

        ev = TelemetryEvent(
            agent_id="a1",
            project_id="test-p",
            run_id="r1",
            environment="development",
            event_type="run_started",
        )
        assert exporter.export([ev]) is True
        assert len(rsps.calls) == 2


def test_http_exporter_fails_immediately_on_non_retryable_403():
    config = AgentOpsConfig(
        api_endpoint="http://testserver",
        project_id="test-p",
        max_retries=3,
        retry_backoff_seconds=0.01,
    )
    exporter = HttpExporter(config)

    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, "http://testserver/v1/telemetry/events", status=403)

        ev = TelemetryEvent(
            agent_id="a1",
            project_id="test-p",
            run_id="r1",
            environment="development",
            event_type="run_started",
        )
        assert exporter.export([ev]) is False
        # Must NOT retry 403
        assert len(rsps.calls) == 1


def test_http_exporter_observes_retry_after_on_429():
    config = AgentOpsConfig(
        api_endpoint="http://testserver",
        project_id="test-p",
        max_retries=1,
        retry_backoff_seconds=0.01,
    )
    exporter = HttpExporter(config)

    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.POST,
            "http://testserver/v1/telemetry/events",
            status=429,
            headers={"Retry-After": "0.05"},
        )
        rsps.add(responses.POST, "http://testserver/v1/telemetry/events", status=202)

        ev = TelemetryEvent(
            agent_id="a1",
            project_id="test-p",
            run_id="r1",
            environment="development",
            event_type="run_started",
        )
        start = time.perf_counter()
        assert exporter.export([ev]) is True
        elapsed = time.perf_counter() - start
        assert elapsed >= 0.02
        exporter_calls = [c for c in rsps.calls if "r1" in c.request.body.decode()]
        assert len(exporter_calls) == 2


def test_http_exporter_connection_error_is_swallowed():
    config = AgentOpsConfig(
        api_endpoint="http://testserver",
        project_id="test-p",
        max_retries=1,
        retry_backoff_seconds=0.01,
    )
    exporter = HttpExporter(config)

    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.POST,
            "http://testserver/v1/telemetry/events",
            body=requests.ConnectionError("Connection refused"),
        )
        rsps.add(
            responses.POST,
            "http://testserver/v1/telemetry/events",
            body=requests.ConnectionError("Connection refused"),
        )

        ev = TelemetryEvent(
            agent_id="a1",
            project_id="test-p",
            run_id="r1",
            environment="development",
            event_type="run_started",
        )
        # Should return False without raising exception
        assert exporter.export([ev]) is False
        assert len(rsps.calls) == 2


def test_sdk_queue_buffer_overflow_drops_safely():
    # Configure tiny queue size
    config = AgentOpsConfig(
        api_endpoint="http://testserver",
        project_id="test-p",
        max_queue_size=5,
        flush_interval_seconds=10.0,  # don't flush automatically
        max_retries=0,
        retry_backoff_seconds=0.01,
    )
    client = AgentOps(config=config)

    # Put 20 events into a queue of size 5
    for i in range(20):
        run = client.start_run(agent_id="a1", run_id=f"r-{i}")
        run.record_event("custom_event")

    # Queue overflow must be handled safely: dropped_events_count must be recorded
    assert client.dropped_events_count > 0
    # Agent execution was uninterrupted
    client.shutdown(timeout=0.1)


def test_sdk_redaction_unconditional_for_credentials():
    data = {
        "api_key": "aop_12345678_secretsecretsecret",
        "nested": {
            "password": "supersecretpassword",
            "token": "sk-1234567890abcdef1234",
            "normal_field": "visible",
            "prompt": "user prompt text",
        }
    }
    # With capture_payloads=False: credentials AND prompt are redacted
    res = redact_sensitive_data(data, capture_payloads=False)
    assert res["api_key"] == "[REDACTED]"
    assert res["nested"]["password"] == "[REDACTED]"
    assert res["nested"]["token"] == "[REDACTED]"
    assert res["nested"]["prompt"] == "[REDACTED]"
    assert res["nested"]["normal_field"] == "visible"

    # With capture_payloads=True: credentials MUST STILL be redacted, prompt is allowed
    res_captured = redact_sensitive_data(data, capture_payloads=True)
    assert res_captured["api_key"] == "[REDACTED]"
    assert res_captured["nested"]["password"] == "[REDACTED]"
    assert res_captured["nested"]["token"] == "[REDACTED]"
    assert res_captured["nested"]["prompt"] == "user prompt text"
