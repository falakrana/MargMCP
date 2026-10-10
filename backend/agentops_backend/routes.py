"""HTTP routes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.orm import Session

from agentops_backend import ingestion, queries, registry
from agentops_backend.auth import (
    Principal,
    get_session,
    require_admin,
    require_project_access,
    require_scope,
)
from agentops_backend.errors import ApiError
from agentops_backend.models import Agent, Project
from agentops_backend.schemas import (
    SAFE_ID_PATTERN,
    AgentCreate,
    AgentOut,
    ApiKeyCreate,
    ApiKeyCreated,
    ErrorSummaryOut,
    IngestResult,
    ProjectCreate,
    ProjectOut,
    RunDetailOut,
    RunListOut,
    RunStatus,
)

health_router = APIRouter(prefix="/health", tags=["health"])
ingest_router = APIRouter(prefix="/v1/telemetry", tags=["ingestion"])
query_router = APIRouter(prefix="/v1/projects", tags=["query"])
admin_router = APIRouter(
    prefix="/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)]
)


# ------------------------------- health ------------------------------------ #
@health_router.get("/live")
def live() -> dict:
    return {"status": "alive"}


@health_router.get("/ready")
def ready(request: Request) -> dict:
    # Deliberately generic: no connection strings or driver errors are exposed.
    try:
        with request.app.state.session_factory() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        raise ApiError(503, "not_ready", "Service is not ready.")
    return {"status": "ready"}


# ------------------------------ ingestion ---------------------------------- #
@ingest_router.post("/events", response_model=IngestResult, status_code=202)
async def post_events(
    request: Request,
    principal: Principal = Depends(require_scope("ingest")),
    session: Session = Depends(get_session),
) -> IngestResult:
    settings = request.app.state.settings
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.max_payload_bytes:
        raise ApiError(
            413, "payload_too_large", f"Request body exceeds {settings.max_payload_bytes} bytes."
        )
    raw = await request.body()
    batch = ingestion.validate_envelope(raw, settings)
    require_project_access(principal, batch.project_id)
    return await run_in_threadpool(
        ingestion.ingest_batch, session, settings, principal.project_id, batch
    )


# -------------------------------- query ------------------------------------ #
def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _range(after: Optional[datetime], before: Optional[datetime]):
    after, before = _utc(after), _utc(before)
    if after and before and after >= before:
        raise ApiError(
            422, "invalid_time_range", "started_after must be earlier than started_before."
        )
    return after, before


def _scoped(principal: Principal, project_id: str) -> None:
    require_project_access(principal, project_id)


@query_router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: str,
    principal: Principal = Depends(require_scope("read")),
    session: Session = Depends(get_session),
) -> ProjectOut:
    _scoped(principal, project_id)
    return queries.get_project(session, project_id)


@query_router.get("/{project_id}/agents", response_model=list[AgentOut])
def list_agents(
    project_id: str,
    principal: Principal = Depends(require_scope("read")),
    session: Session = Depends(get_session),
) -> list[AgentOut]:
    _scoped(principal, project_id)
    return queries.list_agents(session, project_id)


@query_router.get("/{project_id}/agents/{agent_id}", response_model=AgentOut)
def get_agent(
    project_id: str,
    agent_id: str,
    principal: Principal = Depends(require_scope("read")),
    session: Session = Depends(get_session),
) -> AgentOut:
    _scoped(principal, project_id)
    return queries.get_agent(session, project_id, agent_id)


@query_router.get("/{project_id}/runs", response_model=RunListOut)
def list_runs(
    project_id: str,
    agent_id: Optional[str] = Query(default=None, pattern=SAFE_ID_PATTERN),
    status: Optional[RunStatus] = None,
    environment: Optional[str] = Query(default=None, max_length=32),
    started_after: Optional[datetime] = None,
    started_before: Optional[datetime] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=queries.MAX_PAGE_SIZE),
    principal: Principal = Depends(require_scope("read")),
    session: Session = Depends(get_session),
) -> RunListOut:
    _scoped(principal, project_id)
    after, before = _range(started_after, started_before)
    return queries.list_runs(
        session,
        project_id,
        agent_id=agent_id,
        status=status,
        environment=environment,
        started_after=after,
        started_before=before,
        page=page,
        page_size=page_size,
    )


@query_router.get("/{project_id}/runs/{run_id}", response_model=RunDetailOut)
def get_run(
    project_id: str,
    run_id: str,
    max_events: int = Query(default=500, ge=1, le=queries.MAX_EVENTS_PER_RUN),
    principal: Principal = Depends(require_scope("read")),
    session: Session = Depends(get_session),
) -> RunDetailOut:
    _scoped(principal, project_id)
    return queries.get_run_detail(session, project_id, run_id, max_events)


@query_router.get("/{project_id}/errors/summary", response_model=ErrorSummaryOut)
def get_error_summary(
    project_id: str,
    agent_id: Optional[str] = Query(default=None, pattern=SAFE_ID_PATTERN),
    started_after: Optional[datetime] = None,
    started_before: Optional[datetime] = None,
    principal: Principal = Depends(require_scope("read")),
    session: Session = Depends(get_session),
) -> ErrorSummaryOut:
    _scoped(principal, project_id)
    after, before = _range(started_after, started_before)
    return queries.error_summary(
        session, project_id, agent_id=agent_id, started_after=after, started_before=before
    )


# -------------------------------- admin ------------------------------------ #
@admin_router.post("/projects", response_model=ProjectOut, status_code=201)
def admin_create_project(
    body: ProjectCreate, session: Session = Depends(get_session)
) -> ProjectOut:
    project: Project = registry.create_project(session, body)
    return queries.get_project(session, project.id)


@admin_router.post("/projects/{project_id}/agents", response_model=AgentOut, status_code=201)
def admin_create_agent(
    project_id: str, body: AgentCreate, session: Session = Depends(get_session)
) -> AgentOut:
    agent: Agent = registry.create_agent(session, project_id, body)
    return queries.get_agent(session, project_id, agent.id)


@admin_router.post(
    "/projects/{project_id}/api-keys", response_model=ApiKeyCreated, status_code=201
)
def admin_create_api_key(
    project_id: str,
    body: ApiKeyCreate,
    request: Request,
    session: Session = Depends(get_session),
) -> ApiKeyCreated:
    return registry.create_api_key(
        session, request.app.state.settings.secret_key, project_id, body
    )
