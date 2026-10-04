import pytest
import responses
from agentops_sdk import AgentOps, AgentOpsConfig
from agentops_sdk.context import get_current_run

@pytest.fixture
def mock_agentops():
    config = AgentOpsConfig(
        api_endpoint="http://testserver",
        project_id="test-project",
        agent_id="test-agent",
        flush_interval_seconds=0.1 # fast flush for tests
    )
    client = AgentOps(config=config)
    yield client
    client.shutdown(timeout=1.0)

@responses.activate
def test_successful_run_lifecycle(mock_agentops):
    responses.add(
        responses.POST,
        "http://testserver/v1/telemetry/events",
        json={"status": "ok"},
        status=200
    )
    
    with mock_agentops.start_run() as run:
        assert run.agent_id == "test-agent"
        assert get_current_run() is run
        run.set_output_summary({"result": "success", "prompt": "secret"})
        
    assert get_current_run() is None
    
    # Wait for background processor to flush
    mock_agentops.shutdown(timeout=1.0)
    
    assert len(responses.calls) >= 1
    payloads = [call.request.body.decode() for call in responses.calls]
    full_payload = "".join(payloads)
    
    assert "run_started" in full_payload
    assert "output_summary" in full_payload
    assert "run_completed" in full_payload
    # Check redaction
    assert "[REDACTED]" in full_payload
    assert "secret" not in full_payload

@responses.activate
def test_failed_run_lifecycle(mock_agentops):
    responses.add(
        responses.POST,
        "http://testserver/v1/telemetry/events",
        json={"status": "ok"},
        status=200
    )
    
    try:
        with mock_agentops.start_run() as run:
            raise ValueError("Test error")
    except ValueError:
        pass
        
    mock_agentops.shutdown(timeout=1.0)
    
    assert len(responses.calls) >= 1
    payloads = [call.request.body.decode() for call in responses.calls]
    full_payload = "".join(payloads)
    
    assert "run_failed" in full_payload
    assert "ValueError" in full_payload
    assert "Test error" in full_payload

@responses.activate
def test_telemetry_failure_does_not_crash_agent(mock_agentops):
    responses.add(
        responses.POST,
        "http://testserver/v1/telemetry/events",
        status=500
    )
    
    # This should not raise an exception even though the backend fails
    with mock_agentops.start_run():
        pass
        
    mock_agentops.shutdown(timeout=1.0)
    # If we reached here, the agent didn't crash.
