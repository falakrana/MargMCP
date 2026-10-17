"""HTTP routes."""
from __future__ import annotations

import hmac
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.orm import Session

from agentops_backend import ingestion, queries, registry, trace_service
from agentops_backend.auth import (
    Principal,
    _bearer_token,
    bearer_scheme,
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
    CorrelationLinks,
    ErrorSummaryOut,
    IngestResult,
    ProjectCreate,
    ProjectOut,
    RunDetailOut,
    RunListOut,
    RunStatus,
    RunTimelineOut,
    SpanOut,
)

health_router = APIRouter(prefix="/health", tags=["health"])
metrics_router = APIRouter(tags=["metrics"])
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


# ------------------------------- metrics ----------------------------------- #
def _require_metrics_access(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> None:
    settings = request.app.state.settings
    configured = settings.metrics_token
    if not configured:
        if settings.env == "development":
            return  # local convenience only; documented in docs/observability.md
        raise ApiError(503, "metrics_disabled", "Metrics endpoint is not enabled on this server.")
    token = credentials.credentials if credentials is not None else _bearer_token(request)
    if token is None or not hmac.compare_digest(token, configured):
        raise ApiError(
            401, "unauthorized", "Missing or invalid metrics credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@metrics_router.get("/metrics", dependencies=[Depends(_require_metrics_access)])
def metrics(request: Request) -> Response:
    registry_ = request.app.state.observability.metrics.registry
    return Response(generate_latest(registry_), media_type=CONTENT_TYPE_LATEST)


# ------------------------------ ingestion ---------------------------------- #
@ingest_router.post("/events", response_model=IngestResult, status_code=202)
async def post_events(
    request: Request,
    principal: Principal = Depends(require_scope("ingest")),
    session: Session = Depends(get_session),
) -> IngestResult:
    settings = request.app.state.settings
    observer = request.app.state.observability
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.max_payload_bytes:
        raise ApiError(
            413, "payload_too_large", f"Request body exceeds {settings.max_payload_bytes} bytes."
        )
    raw = await request.body()
    batch = ingestion.validate_envelope(raw, settings)
    require_project_access(principal, batch.project_id)
    with observer.ingest_span(principal.project_id) as span:
        result = await run_in_threadpool(
            ingestion.ingest_batch, session, settings, principal.project_id, batch, observer
        )
        if span is not None:
            span.set_attribute("agentops.batch_size", len(batch.batch))
            span.set_attribute("agentops.accepted", result.accepted)
            span.set_attribute("agentops.duplicates", result.duplicates)
            span.set_attribute("agentops.rejected", len(result.rejected))
    return result


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


# ---- Phase 5: trace details and run history -------------------------------- #

@query_router.get(
    "/{project_id}/runs/{run_id}/timeline",
    response_model=RunTimelineOut,
    summary="Run timeline (Phase 5)",
    description=(
        "Returns the full explainable timeline for a single run, including "
        "assembled spans in parent-child order, raw paginated events, "
        "completeness flags, and cross-signal correlation links."
    ),
)
def get_run_timeline(
    project_id: str,
    run_id: str,
    # Span pagination
    max_spans: int = Query(
        default=trace_service.MAX_SPANS_PER_TRACE,
        ge=1,
        le=trace_service.MAX_SPANS_PER_TRACE,
        description="Maximum number of spans to return.",
    ),
    # Event pagination (independent of spans)
    event_page: int = Query(default=1, ge=1),
    event_page_size: int = Query(
        default=100, ge=1, le=trace_service.MAX_EVENTS_PER_PAGE
    ),
    principal: Principal = Depends(require_scope("read")),
    session: Session = Depends(get_session),
    request: Request = None,  # type: ignore[assignment]
) -> RunTimelineOut:
    _scoped(principal, project_id)
    settings = request.app.state.settings
    result = trace_service.get_run_timeline(
        session,
        project_id,
        run_id,
        include_payload_summary=settings.payload_capture_enabled,
        max_spans=max_spans,
        event_page=event_page,
        event_page_size=event_page_size,
        otlp_base_url=settings.otlp_ui_base_url,
        trace_retention_days=settings.trace_retention_days,
        run_retention_days=settings.run_retention_days,
    )
    # Serialise SpanInfo objects (not Pydantic) → SpanOut
    spans_out = [
        SpanOut(
            span_id=s.span_id,
            parent_span_id=s.parent_span_id,
            name=s.name,
            event_id=s.event_id,
            event_type=s.event_type,
            start_time=s.start_time,
            end_time=s.end_time,
            duration_ms=s.duration_ms,
            status=s.status,
            attributes=s.attributes,
            parent_missing=s.parent_missing,
        )
        for s in result.spans
    ]
    cl = result.correlation_links
    return RunTimelineOut(
        run=result.run,
        is_complete=result.is_complete,
        trace_data_may_have_expired=result.trace_data_may_have_expired,
        spans=spans_out,
        spans_truncated=result.spans_truncated,
        span_count=len(spans_out),
        events=result.events,
        total_event_count=result.total_event_count,
        event_page=result.event_page,
        event_page_size=result.event_page_size,
        trace_link=result.trace_link,
        correlation_links=CorrelationLinks(
            run_id=cl["run_id"],
            trace_id=cl["trace_id"],
            root_span_id=cl["root_span_id"],
            run_metadata_expires_at=cl["run_metadata_expires_at"],
            trace_data_expires_at=cl["trace_data_expires_at"],
            metric_window=cl.get("metric_window"),
        ),
    )


@query_router.get(
    "/{project_id}/runs/by-trace/{trace_id}",
    summary="Look up run by OTLP trace ID (Phase 5)",
    description=(
        "Redirects (307) to the run detail endpoint for the run whose "
        "OpenTelemetry trace_id matches the given value. Useful for jumping "
        "from a Tempo / Jaeger trace to the AgentOps run record."
    ),
)
def get_run_by_trace_id(
    project_id: str,
    trace_id: str,
    principal: Principal = Depends(require_scope("read")),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    _scoped(principal, project_id)
    run = trace_service.get_run_by_trace_id(session, project_id, trace_id)
    return RedirectResponse(
        url=f"/v1/projects/{project_id}/runs/{run.run_id}/timeline",
        status_code=307,
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
