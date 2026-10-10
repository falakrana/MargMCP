"""Seed SYNTHETIC demo data for local development.

Everything created here is fake and labelled as such (project name, agent
names, run metadata ``synthetic=true``). Never run against production.

    python -m agentops_backend.seed

Prints a freshly generated demo API key once. Requires the schema to exist
(``alembic upgrade head`` or AGENTOPS_AUTO_CREATE_TABLES=true).
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone

from agentops_backend import ingestion, registry
from agentops_backend.config import get_settings
from agentops_backend.db import make_engine, make_session_factory
from agentops_backend.models import Agent, Base, Project
from agentops_backend.schemas import (
    AgentCreate,
    ApiKeyCreate,
    IngestBatch,
    ProjectCreate,
)

DEMO_PROJECT_ID = "synthetic-demo"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_events(agent_id: str, rng: random.Random, start: datetime, fail: bool) -> list[dict]:
    run_id = f"synthetic-{uuid.UUID(int=rng.getrandbits(128))}"

    def ev(kind: str, offset: float, data: dict | None = None) -> dict:
        return {
            "schema_version": "1.0",
            "event_id": str(uuid.UUID(int=rng.getrandbits(128))),
            "agent_id": agent_id,
            "run_id": run_id,
            "event_type": kind,
            "timestamp": _iso(start + timedelta(seconds=offset)),
            "environment": "development",
            "data": data or {},
        }

    events = [
        ev("run_started", 0, {
            "trace_id": uuid.UUID(int=rng.getrandbits(128)).hex,
            "root_span_id": uuid.UUID(int=rng.getrandbits(128)).hex[:16],
            "metadata": {"synthetic": "true"},
        }),
        ev("llm_call_completed", 1, {
            "provider": "synthetic", "model": "demo-model",
            "prompt_tokens": rng.randint(50, 500), "completion_tokens": rng.randint(10, 200),
        }),
        ev("tool_call_completed", 2, {"tool_name": "synthetic_search"}),
    ]
    if fail:
        events.append(ev("run_failed", 3, {
            "error_type": rng.choice(["TimeoutError", "ToolError", "RateLimitError"]),
            "error_summary": "synthetic demo failure",
        }))
    else:
        events.append(ev("run_completed", 3))
    return events


def seed(run_count: int = 30, seed_value: int = 42) -> str:
    settings = get_settings()
    engine = make_engine(settings.resolved_database_url())
    Base.metadata.create_all(engine)  # no-op when migrations already ran
    factory = make_session_factory(engine)
    rng = random.Random(seed_value)
    with factory() as session:
        if session.get(Project, DEMO_PROJECT_ID) is None:
            registry.create_project(
                session, ProjectCreate(name="SYNTHETIC DEMO PROJECT", project_id=DEMO_PROJECT_ID)
            )
        agents = ["synthetic-support-agent", "synthetic-research-agent"]
        for a in agents:
            if session.get(Agent, (DEMO_PROJECT_ID, a)) is None:
                registry.create_agent(session, DEMO_PROJECT_ID, AgentCreate(name=a, agent_id=a))
        key = registry.create_api_key(
            session, settings.secret_key, DEMO_PROJECT_ID, ApiKeyCreate(name="synthetic-demo-key")
        )
        now = datetime.now(timezone.utc)
        for i in range(run_count):
            start = now - timedelta(minutes=(run_count - i) * 5)
            events = build_events(rng.choice(agents), rng, start, fail=rng.random() < 0.25)
            batch = IngestBatch.model_validate(
                {"schema_version": "1.0", "project_id": DEMO_PROJECT_ID, "batch": events}
            )
            ingestion.ingest_batch(session, settings, DEMO_PROJECT_ID, batch)
    return key.api_key


if __name__ == "__main__":
    api_key = seed()
    print("Synthetic demo data created (project 'synthetic-demo').")
    print(f"Demo API key (shown once, ingest+read): {api_key}")
