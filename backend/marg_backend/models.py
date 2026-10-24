"""SQLAlchemy models.

Isolation design: every tenant-owned table has ``project_id`` as the leading
part of its primary key, so an identifier submitted by one project can never
collide with or overwrite another project's rows.

Indexes (each backs a real query in ``query/service.py``):

* ``ix_runs_project_started``         — default run listing / time range
* ``ix_runs_project_agent_started``   — filter runs by agent
* ``ix_runs_project_status_started``  — filter runs by status
* ``ix_runs_project_env_started``     — filter runs by environment
* ``ix_runs_project_error``           — error summary grouping
* ``ix_events_project_run_ts``        — fetch a run's events in order
* ``uq_api_keys_prefix``              — API key lookup during auth
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JSONType = JSON().with_variant(JSONB(), "postgresql")


class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC datetimes on every backend (SQLite drops tzinfo)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Optional[datetime], dialect: Any):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime not allowed; use UTC-aware values")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: Optional[datetime], dialect: Any):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class Agent(Base):
    __tablename__ = "agents"

    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    auto_registered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (Index("uq_api_keys_prefix", "key_prefix", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    # HMAC-SHA256 of the key; the plaintext key is never stored.
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes: Mapped[str] = mapped_column(String(64), nullable=False)  # "ingest,read"
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "agent_id"], ["agents.project_id", "agents.id"]
        ),
        Index("ix_runs_project_started", "project_id", "started_at"),
        Index("ix_runs_project_agent_started", "project_id", "agent_id", "started_at"),
        Index("ix_runs_project_status_started", "project_id", "status", "started_at"),
        Index("ix_runs_project_env_started", "project_id", "environment", "started_at"),
        Index("ix_runs_project_error", "project_id", "status", "error_type"),
    )

    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id"), primary_key=True
    )
    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(32), nullable=False)
    root_span_id: Mapped[str] = mapped_column(String(16), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    error_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    error_summary: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    deployment_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sdk_version: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    llm_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_prompt_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_completion_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    run_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSONType, nullable=True)
    # True once a real ``run_started`` has been seen (events may arrive out of order).
    start_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "run_id"], ["runs.project_id", "runs.run_id"]
        ),
        Index("ix_events_project_run_ts", "project_id", "run_id", "timestamp"),
    )

    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id"), primary_key=True
    )
    # event_id is the idempotency key, scoped to the project.
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    data: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
