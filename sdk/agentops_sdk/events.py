from pydantic import BaseModel, Field, field_validator
from typing import Dict, Optional, Any, Literal
import uuid
from datetime import datetime, timezone

def generate_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

class TelemetryEvent(BaseModel):
    """Canonical Telemetry Event Model (Schema v1.0)"""
    schema_version: Literal["1.0"] = "1.0"
    event_id: str = Field(default_factory=generate_uuid)
    agent_id: str
    project_id: str
    run_id: str
    environment: str
    timestamp: str = Field(default_factory=utc_now)
    event_type: str
    deployment_version: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    
class EventBatchPayload(BaseModel):
    """Payload for submitting a batch of events"""
    schema_version: Literal["1.0"] = "1.0"
    project_id: str
    batch: list[TelemetryEvent]
