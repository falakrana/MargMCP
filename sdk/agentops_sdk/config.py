import os
from pydantic import BaseModel, Field
from typing import Optional

class AgentOpsConfig(BaseModel):
    """Configuration for the AgentOps SDK."""
    api_endpoint: str = Field(default="http://localhost:8000")
    api_key: Optional[str] = None
    project_id: Optional[str] = None
    agent_id: Optional[str] = None
    environment: str = Field(default="development")
    deployment_version: Optional[str] = None
    
    # Exporter and buffering
    flush_interval_seconds: float = Field(default=2.0)
    max_batch_size: int = Field(default=100)
    max_queue_size: int = Field(default=1000)
    timeout_seconds: float = Field(default=5.0)
    
    # Privacy
    capture_payloads: bool = Field(default=False)
    
    @classmethod
    def from_env(cls) -> "AgentOpsConfig":
        """Load configuration from environment variables."""
        return cls(
            api_endpoint=os.getenv("AGENTOPS_API_ENDPOINT", "http://localhost:8000"),
            api_key=os.getenv("AGENTOPS_API_KEY"),
            project_id=os.getenv("AGENTOPS_PROJECT_ID"),
            agent_id=os.getenv("AGENTOPS_AGENT_ID"),
            environment=os.getenv("AGENTOPS_ENV", "development"),
            deployment_version=os.getenv("AGENTOPS_DEPLOYMENT_VERSION"),
            capture_payloads=os.getenv("AGENTOPS_CAPTURE_PAYLOADS", "false").lower() == "true",
        )
