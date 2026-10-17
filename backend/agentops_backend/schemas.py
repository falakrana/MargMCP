"""Pydantic request/response schemas (match docs/telemetry-schema.md v1.0)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

SUPPORTED_SCHEMA_VERSIONS = {"1.0"}
SAFE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$"

EventType = Literal[
    "run_started",
    "run_completed",
    "run_failed",
    "run_cancelled",
    "llm_call_started",
    "llm_call_completed",
    "llm_call_failed",
    "tool_call_started",
    "tool_call_completed",
    "tool_call_failed",
    "custom_event",
    # Emitted by the Phase 2 SDK (Run.set_output_summary); not in the v1 doc table.
    "output_summary",
]
Environment = Literal["development", "staging", "production"]
RunStatus = Literal["running", "success", "error", "cancelled", "unknown"]


# --------------------------------------------------------------------------- #
# Ingestion
# --------------------------------------------------------------------------- #
class IngestEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    event_id: str = Field(pattern=SAFE_ID_PATTERN)
    agent_id: str = Field(pattern=SAFE_ID_PATTERN)
    run_id: str = Field(pattern=SAFE_ID_PATTERN)
    event_type: EventType
    timestamp: datetime
    environment: Environment
    deployment_version: Optional[str] = Field(default=None, max_length=64)
    # Project is also at batch level; an optional per-event copy must match it.
    project_id: Optional[str] = Field(default=None, pattern=SAFE_ID_PATTERN)
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp", mode="before")
    @classmethod
    def _timestamp_must_be_iso_string(cls, v: Any) -> Any:
        if not isinstance(v, str):
            raise ValueError("timestamp must be an ISO-8601 string")
        return v

    @field_validator("timestamp")
    @classmethod
    def _timestamp_must_have_tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamp must include a UTC offset (e.g. 'Z')")
        return v.astimezone(timezone.utc)


class IngestBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    project_id: str = Field(pattern=SAFE_ID_PATTERN)
    batch: list[IngestEvent] = Field(min_length=1)


class RejectedEvent(BaseModel):
    index: int
    event_id: Optional[str] = None
    code: str
    message: str


class IngestResult(BaseModel):
    accepted: int
    duplicates: int
    rejected: list[RejectedEvent]


# --------------------------------------------------------------------------- #
# Admin
# --------------------------------------------------------------------------- #
class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    tenant_id: str = Field(default="default", pattern=SAFE_ID_PATTERN)
    project_id: Optional[str] = Field(default=None, pattern=SAFE_ID_PATTERN)


class AgentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    agent_id: Optional[str] = Field(default=None, pattern=SAFE_ID_PATTERN)


class ApiKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    scopes: list[Literal["ingest", "read"]] = Field(default=["ingest", "read"], min_length=1)


class ApiKeyCreated(BaseModel):
    id: int
    project_id: str
    name: str
    scopes: list[str]
    api_key: str = Field(description="Shown exactly once; store it securely.")


# --------------------------------------------------------------------------- #
# Query responses
# --------------------------------------------------------------------------- #
class ProjectOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    created_at: datetime
    agent_count: int


class AgentOut(BaseModel):
    id: str
    project_id: str
    name: str
    auto_registered: bool
    created_at: datetime
    run_count: int
    last_run_at: Optional[datetime] = None


class RunOut(BaseModel):
    run_id: str
    agent_id: str
    project_id: str
    trace_id: str
    root_span_id: str
    environment: str
    status: RunStatus
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    error_type: Optional[str] = None
    error_summary: Optional[str] = None
    deployment_version: Optional[str] = None
    sdk_version: str
    llm_call_count: int
    tool_call_count: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    metadata: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class EventOut(BaseModel):
    event_id: str
    run_id: str
    agent_id: str
    event_type: str
    environment: str
    timestamp: datetime
    data: dict[str, Any]


class RunListOut(BaseModel):
    items: list[RunOut]
    total: int
    page: int
    page_size: int


class RunDetailOut(BaseModel):
    run: RunOut
    events: list[EventOut]
    event_count: int
    events_truncated: bool


class ErrorGroup(BaseModel):
    agent_id: str
    error_type: Optional[str]
    count: int
    last_seen: datetime


class ErrorSummaryOut(BaseModel):
    total_runs: int
    error_runs: int
    groups: list[ErrorGroup]


# --------------------------------------------------------------------------- #
# Phase 5 — Trace Details and Run History
# --------------------------------------------------------------------------- #

class SpanOut(BaseModel):
    """One assembled span in the run timeline."""

    span_id: str
    parent_span_id: Optional[str] = None
    name: str
    event_id: str  # empty string for the synthesised root span
    event_type: str
    start_time: datetime
    end_time: datetime
    duration_ms: Optional[int] = None
    status: str  # "ok" | "error" | "cancelled" | "running"
    attributes: dict[str, Any]
    # True when this span references a parent that is not in the result set
    # (e.g. the parent arrived in a different paginated batch or was missing).
    parent_missing: bool = False


class CorrelationLinks(BaseModel):
    """Cross-signal links for a single run."""

    run_id: str
    trace_id: str
    root_span_id: str
    # ISO-8601; after this timestamp the run record (events table) may be gone.
    run_metadata_expires_at: str
    # ISO-8601; after this timestamp the OTLP backend may have purged the trace.
    trace_data_expires_at: str
    # Half-open UTC window that covers this run in Prometheus/metric queries.
    metric_window: Optional[dict[str, str]] = None


class RunTimelineOut(BaseModel):
    """Full explainable timeline for one run (Phase 5 primary response)."""

    run: RunOut
    # False when the run has no terminal event or ended_at is still NULL.
    is_complete: bool
    # True when the run started more than ``trace_retention_days`` ago;
    # the local timeline is still served but the OTLP backend may return nothing.
    trace_data_may_have_expired: bool
    # Span tree assembled from local event storage.
    spans: list[SpanOut]
    spans_truncated: bool
    span_count: int
    # Raw event page (independent pagination from spans).
    events: list[EventOut]
    total_event_count: int
    event_page: int
    event_page_size: int
    # Deep-link into the configured OTLP UI; None when no UI URL is configured.
    trace_link: Optional[str] = None
    correlation_links: CorrelationLinks
