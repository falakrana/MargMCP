"""Backend configuration (environment-driven, no secrets in code)."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "change-me-to-a-random-string"


class Settings(BaseSettings):
    """Settings loaded from ``AGENTOPS_*`` environment variables.

    The database URL is taken from ``AGENTOPS_DATABASE_URL`` when set;
    otherwise it is assembled from the ``POSTGRES_*`` variables.
    """

    model_config = SettingsConfigDict(
        env_prefix="AGENTOPS_", env_file=".env", extra="ignore"
    )

    env: str = "development"
    secret_key: str = DEFAULT_SECRET_KEY
    log_level: str = "INFO"

    database_url: Optional[str] = None
    # Admin bootstrap token for project/agent/key management. Admin API is
    # disabled (503) when unset.
    admin_token: Optional[str] = None
    # Dev convenience only; production should use Alembic migrations.
    auto_create_tables: bool = False

    max_payload_bytes: int = Field(default=1_048_576, ge=1024)
    max_batch_size: int = Field(default=100, ge=1)
    max_event_data_bytes: int = Field(default=16_384, ge=256)
    timestamp_tolerance_hours: int = Field(default=24, ge=1)
    auto_register_agents: bool = True

    # ---- Phase 4: observability ----
    # Bearer token required to scrape GET /metrics. When unset, /metrics is open
    # in development and disabled (503) in any other environment.
    metrics_token: Optional[str] = None
    # OTLP/HTTP traces endpoint (e.g. http://localhost:4318/v1/traces). Tracing
    # export is disabled when unset.
    otlp_endpoint: Optional[str] = None
    service_name: str = "agentops-backend"
    # Fraction of non-error traces exported. Error traces are always exported.
    trace_sample_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    # Bounded in-memory span queue; spans are dropped (and counted) when full.
    trace_queue_size: int = Field(default=2048, ge=1)
    trace_export_timeout_seconds: int = Field(default=5, ge=1)

    # ---- Phase 5: trace details and run history ----
    # When True, optional payload summaries (output_summary etc.) may be
    # included in timeline responses. Off by default to protect privacy.
    payload_capture_enabled: bool = False
    # How many days run records (runs + events tables) are kept.
    run_retention_days: int = Field(default=90, ge=1)
    # How many days the OTLP trace backend (Tempo) retains traces.
    # Used only for ``trace_data_may_have_expired`` computation; this service
    # does not enforce Tempo's retention policy.
    trace_retention_days: int = Field(default=30, ge=1)
    # Base URL of the Grafana / OTLP UI used to generate deep-links.
    # Example: http://localhost:3000
    otlp_ui_base_url: Optional[str] = None

    postgres_host: str = Field(default="localhost", validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, validation_alias="POSTGRES_PORT")
    postgres_db: str = Field(default="agentops", validation_alias="POSTGRES_DB")
    postgres_user: str = Field(default="agentops", validation_alias="POSTGRES_USER")
    postgres_password: str = Field(default="", validation_alias="POSTGRES_PASSWORD")

    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        return (
            f"postgresql+psycopg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def validate_for_runtime(self) -> None:
        """Refuse to start outside development with an insecure secret."""
        if self.env != "development" and (
            self.secret_key == DEFAULT_SECRET_KEY or len(self.secret_key) < 32
        ):
            raise RuntimeError(
                "AGENTOPS_SECRET_KEY must be set to a random value of at least "
                "32 characters when AGENTOPS_ENV is not 'development'."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
