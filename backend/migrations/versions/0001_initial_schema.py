"""Initial schema: projects, agents, api_keys, runs, events.

Revision ID: 0001
Revises:
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "agents",
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), primary_key=True),
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("auto_registered", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("scopes", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("uq_api_keys_prefix", "api_keys", ["key_prefix"], unique=True)

    op.create_table(
        "runs",
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), primary_key=True),
        sa.Column("run_id", sa.String(64), primary_key=True),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("trace_id", sa.String(32), nullable=False),
        sa.Column("root_span_id", sa.String(16), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.BigInteger, nullable=True),
        sa.Column("error_type", sa.String(128), nullable=True),
        sa.Column("error_summary", sa.String(1024), nullable=True),
        sa.Column("deployment_version", sa.String(64), nullable=True),
        sa.Column("sdk_version", sa.String(32), nullable=False),
        sa.Column("llm_call_count", sa.Integer, nullable=False),
        sa.Column("tool_call_count", sa.Integer, nullable=False),
        sa.Column("total_prompt_tokens", sa.BigInteger, nullable=False),
        sa.Column("total_completion_tokens", sa.BigInteger, nullable=False),
        sa.Column("total_tokens", sa.BigInteger, nullable=False),
        sa.Column("metadata", JSONType, nullable=True),
        sa.Column("start_confirmed", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id", "agent_id"], ["agents.project_id", "agents.id"]),
    )
    op.create_index("ix_runs_project_started", "runs", ["project_id", "started_at"])
    op.create_index(
        "ix_runs_project_agent_started", "runs", ["project_id", "agent_id", "started_at"]
    )
    op.create_index(
        "ix_runs_project_status_started", "runs", ["project_id", "status", "started_at"]
    )
    op.create_index(
        "ix_runs_project_env_started", "runs", ["project_id", "environment", "started_at"]
    )
    op.create_index("ix_runs_project_error", "runs", ["project_id", "status", "error_type"])

    op.create_table(
        "events",
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), primary_key=True),
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", JSONType, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id", "run_id"], ["runs.project_id", "runs.run_id"]),
    )
    op.create_index("ix_events_project_run_ts", "events", ["project_id", "run_id", "timestamp"])


def downgrade() -> None:
    op.drop_index("ix_events_project_run_ts", table_name="events")
    op.drop_table("events")
    for name in (
        "ix_runs_project_error",
        "ix_runs_project_env_started",
        "ix_runs_project_status_started",
        "ix_runs_project_agent_started",
        "ix_runs_project_started",
    ):
        op.drop_index(name, table_name="runs")
    op.drop_table("runs")
    op.drop_index("uq_api_keys_prefix", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_table("agents")
    op.drop_table("projects")
