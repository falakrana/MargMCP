"""Query service. Every function takes ``project_id`` and filters on it, so
tenant scoping is enforced here (not only at the HTTP layer)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentops_backend.errors import not_found
from agentops_backend.models import Agent, Event, Project, Run
from agentops_backend.schemas import (
    AgentOut,
    ErrorGroup,
    ErrorSummaryOut,
    EventOut,
    ProjectOut,
    RunDetailOut,
    RunListOut,
    RunOut,
)

MAX_PAGE_SIZE = 100
MAX_EVENTS_PER_RUN = 1000


def run_to_out(r: Run) -> RunOut:
    return RunOut(
        run_id=r.run_id,
        agent_id=r.agent_id,
        project_id=r.project_id,
        trace_id=r.trace_id,
        root_span_id=r.root_span_id,
        environment=r.environment,
        status=r.status,
        started_at=r.started_at,
        ended_at=r.ended_at,
        duration_ms=r.duration_ms,
        error_type=r.error_type,
        error_summary=r.error_summary,
        deployment_version=r.deployment_version,
        sdk_version=r.sdk_version,
        llm_call_count=r.llm_call_count,
        tool_call_count=r.tool_call_count,
        total_prompt_tokens=r.total_prompt_tokens,
        total_completion_tokens=r.total_completion_tokens,
        total_tokens=r.total_tokens,
        metadata=r.run_metadata,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def get_project(session: Session, project_id: str) -> ProjectOut:
    p = session.get(Project, project_id)
    if p is None:
        raise not_found("Project not found.")
    count = session.execute(
        select(func.count()).select_from(Agent).where(Agent.project_id == project_id)
    ).scalar_one()
    return ProjectOut(
        id=p.id, tenant_id=p.tenant_id, name=p.name, created_at=p.created_at, agent_count=count
    )


def _agent_out(a: Agent, run_count: int, last_run_at: Optional[datetime]) -> AgentOut:
    return AgentOut(
        id=a.id,
        project_id=a.project_id,
        name=a.name,
        auto_registered=a.auto_registered,
        created_at=a.created_at,
        run_count=run_count,
        last_run_at=last_run_at,
    )


def list_agents(session: Session, project_id: str) -> list[AgentOut]:
    stats = {
        row.agent_id: (row.n, row.last)
        for row in session.execute(
            select(
                Run.agent_id, func.count().label("n"), func.max(Run.started_at).label("last")
            )
            .where(Run.project_id == project_id)
            .group_by(Run.agent_id)
        )
    }
    agents = session.execute(
        select(Agent).where(Agent.project_id == project_id).order_by(Agent.id)
    ).scalars()
    return [_agent_out(a, *stats.get(a.id, (0, None))) for a in agents]


def get_agent(session: Session, project_id: str, agent_id: str) -> AgentOut:
    a = session.get(Agent, (project_id, agent_id))
    if a is None:
        raise not_found("Agent not found.")
    n, last = session.execute(
        select(func.count(), func.max(Run.started_at)).where(
            Run.project_id == project_id, Run.agent_id == agent_id
        )
    ).one()
    return _agent_out(a, n, last)


def list_runs(
    session: Session,
    project_id: str,
    *,
    agent_id: Optional[str] = None,
    status: Optional[str] = None,
    environment: Optional[str] = None,
    started_after: Optional[datetime] = None,
    started_before: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 25,
) -> RunListOut:
    """Time range is half-open: ``started_after <= started_at < started_before``."""
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    page = max(1, page)
    conds = [Run.project_id == project_id]
    if agent_id:
        conds.append(Run.agent_id == agent_id)
    if status:
        conds.append(Run.status == status)
    if environment:
        conds.append(Run.environment == environment)
    if started_after:
        conds.append(Run.started_at >= started_after)
    if started_before:
        conds.append(Run.started_at < started_before)

    total = session.execute(select(func.count()).select_from(Run).where(*conds)).scalar_one()
    rows = (
        session.execute(
            select(Run)
            .where(*conds)
            .order_by(Run.started_at.desc(), Run.run_id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        .scalars()
        .all()
    )
    return RunListOut(
        items=[run_to_out(r) for r in rows], total=total, page=page, page_size=page_size
    )


def get_run_detail(
    session: Session, project_id: str, run_id: str, max_events: int = MAX_EVENTS_PER_RUN
) -> RunDetailOut:
    run = session.get(Run, (project_id, run_id))
    if run is None:
        raise not_found("Run not found.")
    max_events = max(1, min(max_events, MAX_EVENTS_PER_RUN))
    total = session.execute(
        select(func.count()).select_from(Event).where(
            Event.project_id == project_id, Event.run_id == run_id
        )
    ).scalar_one()
    events = (
        session.execute(
            select(Event)
            .where(Event.project_id == project_id, Event.run_id == run_id)
            .order_by(Event.timestamp, Event.event_id)
            .limit(max_events)
        )
        .scalars()
        .all()
    )
    return RunDetailOut(
        run=run_to_out(run),
        events=[
            EventOut(
                event_id=e.event_id,
                run_id=e.run_id,
                agent_id=e.agent_id,
                event_type=e.event_type,
                environment=e.environment,
                timestamp=e.timestamp,
                data=e.data,
            )
            for e in events
        ],
        event_count=total,
        events_truncated=total > len(events),
    )


def error_summary(
    session: Session,
    project_id: str,
    *,
    agent_id: Optional[str] = None,
    started_after: Optional[datetime] = None,
    started_before: Optional[datetime] = None,
    limit: int = 50,
) -> ErrorSummaryOut:
    conds = [Run.project_id == project_id]
    if agent_id:
        conds.append(Run.agent_id == agent_id)
    if started_after:
        conds.append(Run.started_at >= started_after)
    if started_before:
        conds.append(Run.started_at < started_before)

    total_runs = session.execute(select(func.count()).select_from(Run).where(*conds)).scalar_one()
    rows = session.execute(
        select(
            Run.agent_id,
            Run.error_type,
            func.count().label("n"),
            func.max(Run.started_at).label("last"),
        )
        .where(*conds, Run.status == "error")
        .group_by(Run.agent_id, Run.error_type)
        .order_by(func.count().desc(), Run.agent_id, Run.error_type)
        .limit(max(1, min(limit, MAX_PAGE_SIZE)))
    ).all()
    groups = [
        ErrorGroup(agent_id=r.agent_id, error_type=r.error_type, count=r.n, last_seen=r.last)
        for r in rows
    ]
    error_runs = session.execute(
        select(func.count()).select_from(Run).where(*conds, Run.status == "error")
    ).scalar_one()
    return ErrorSummaryOut(total_runs=total_runs, error_runs=error_runs, groups=groups)
