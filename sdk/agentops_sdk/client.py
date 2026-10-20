from __future__ import annotations
import uuid
import uuid
from typing import Optional, Dict, Any
from types import TracebackType
import logging

from agentops_sdk.config import AgentOpsConfig
from agentops_sdk.events import TelemetryEvent, utc_now
from agentops_sdk.context import set_current_run, reset_current_run
from agentops_sdk.exporters.http import HttpExporter
from agentops_sdk.exporters.batch import AsyncBatchProcessor
from agentops_sdk.redaction import redact_sensitive_data

logger = logging.getLogger(__name__)

class Run:
    """Represents a single execution of an AI agent."""
    
    def __init__(self, client: "AgentOps", agent_id: str, run_id: Optional[str] = None):
        self.client = client
        self.agent_id = agent_id
        self.run_id = run_id or str(uuid.uuid4())
        self.trace_id = uuid.uuid4().hex
        self.root_span_id = uuid.uuid4().hex[:16]
        self._token = None
        
    def __enter__(self) -> "Run":
        self._token = set_current_run(self)
        self.record_event("run_started", data={
            "trace_id": self.trace_id,
            "root_span_id": self.root_span_id
        })
        return self
        
    def __exit__(self, exc_type: Optional[type], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]) -> None:
        if exc_type is not None:
            self.record_event("run_failed", data={
                "error_type": exc_type.__name__,
                "error_summary": str(exc_val)[:1024]
            })
        else:
            self.record_event("run_completed")
            
        if self._token:
            reset_current_run(self._token)
            self._token = None
            
    def set_output_summary(self, summary: Dict[str, Any]) -> None:
        """Record an output summary event."""
        redacted = redact_sensitive_data(summary, self.client.config.capture_payloads)
        self.record_event("output_summary", data={"summary": redacted})
        
    def record_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Record a raw telemetry event associated with this run."""
        event = TelemetryEvent(
            agent_id=self.agent_id,
            project_id=self.client.config.project_id or "default",
            run_id=self.run_id,
            environment=self.client.config.environment,
            event_type=event_type,
            deployment_version=self.client.config.deployment_version,
            data=data or {}
        )
        self.client.processor.add_event(event)

class AgentOps:
    """Main AgentOps client for instrumenting agents."""
    
    def __init__(self, config: Optional[AgentOpsConfig] = None):
        self.config = config or AgentOpsConfig()
        
        if not self.config.project_id:
            logger.warning("AgentOps: project_id is not set. Telemetry may be rejected by the backend.")
            
        self.exporter = HttpExporter(self.config)
        self.processor = AsyncBatchProcessor(self.exporter, self.config)
        
    @classmethod
    def from_env(cls) -> "AgentOps":
        """Initialize the client using environment variables."""
        return cls(config=AgentOpsConfig.from_env())
        
    def start_run(self, agent_id: Optional[str] = None, run_id: Optional[str] = None) -> Run:
        """Start a new agent run."""
        resolved_agent_id = agent_id or self.config.agent_id or "default"
        return Run(self, resolved_agent_id, run_id)
        
    @property
    def dropped_events_count(self) -> int:
        """Return the count of events dropped due to queue overflow."""
        return self.processor.dropped_events_count

    def shutdown(self, timeout: float = 5.0) -> None:
        """Flush remaining telemetry and stop the background processor."""
        self.processor.shutdown(timeout=timeout)
