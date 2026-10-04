import requests
import logging
from typing import List
from agentops_sdk.events import TelemetryEvent, EventBatchPayload
from agentops_sdk.exporters.base import BaseExporter
from agentops_sdk.config import AgentOpsConfig

logger = logging.getLogger(__name__)

class HttpExporter(BaseExporter):
    """Exports telemetry events via HTTP to the AgentOps ingestion API."""
    
    def __init__(self, config: AgentOpsConfig):
        self.config = config
        self.endpoint = f"{config.api_endpoint.rstrip('/')}/v1/telemetry/events"
        self.session = requests.Session()
        if config.api_key:
            self.session.headers.update({"Authorization": f"Bearer {config.api_key}"})
            
    def export(self, events: List[TelemetryEvent]) -> bool:
        if not events:
            return True
            
        # Group by project_id as required by the batch payload schema
        # For MVP, we assume all events in a batch belong to the configured project_id.
        project_id = self.config.project_id
        if not project_id:
            # If no project_id config, try to infer from first event
            project_id = events[0].project_id
            
        payload = EventBatchPayload(
            project_id=project_id,
            batch=events
        )
        
        try:
            response = self.session.post(
                self.endpoint,
                json=payload.model_dump(),
                timeout=self.config.timeout_seconds
            )
            response.raise_for_status()
            return True
        except Exception as e:
            # We catch all exceptions so telemetry failures don't crash the agent
            logger.debug(f"Failed to export telemetry: {e}")
            return False

    def shutdown(self):
        self.session.close()
