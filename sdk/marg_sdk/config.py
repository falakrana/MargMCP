import os
from pydantic import BaseModel, Field
from typing import Optional

class MargConfig(BaseModel):
    """Configuration for the Marg MCP SDK."""
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
    max_retries: int = Field(default=2, ge=0, le=5)
    retry_backoff_seconds: float = Field(default=0.5, ge=0.0)
    
    # Privacy
    capture_payloads: bool = Field(default=False)
    
    @classmethod
    def from_env(cls) -> "MargConfig":
        """Load configuration from environment variables (supports MARG_* and AGENTOPS_* fallback)."""
        def _get(key: str, default: Optional[str] = None) -> Optional[str]:
            return os.getenv(f"MARG_{key}", os.getenv(f"AGENTOPS_{key}", default))

        cap = _get("CAPTURE_PAYLOADS", "false")
        return cls(
            api_endpoint=_get("API_ENDPOINT", "http://localhost:8000"),
            api_key=_get("API_KEY"),
            project_id=_get("PROJECT_ID"),
            agent_id=_get("AGENT_ID"),
            environment=_get("ENV", "development"),
            deployment_version=_get("DEPLOYMENT_VERSION"),
            capture_payloads=str(cap).lower() == "true",
        )

# Backwards compatibility alias
AgentOpsConfig = MargConfig
