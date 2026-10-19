"""FastAPI application factory."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from agentops_backend import __version__
from agentops_backend.assistant import build_provider
from agentops_backend.config import Settings, get_settings
from agentops_backend.db import make_engine, make_session_factory
from agentops_backend.errors import ApiError
from agentops_backend.models import Base
from agentops_backend.observability import INGEST_ENDPOINT, Observability, timer
from agentops_backend.routes import (
    admin_router,
    health_router,
    ingest_router,
    metrics_router,
    query_router,
)

logger = logging.getLogger("agentops_backend")


def _validation_details(errors: list[dict]) -> list[dict]:
    # Only location/message/type: never echo the offending input value.
    return [
        {"loc": [str(p) for p in e.get("loc", ())], "msg": e.get("msg", ""), "type": e.get("type", "")}
        for e in errors
    ]


def create_app(settings: Optional[Settings] = None, span_exporter=None) -> FastAPI:
    settings = settings or get_settings()
    settings.validate_for_runtime()
    logging.basicConfig(level=settings.log_level.upper())

    engine = make_engine(settings.resolved_database_url())
    observability = Observability(settings, span_exporter=span_exporter)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.auto_create_tables:
            Base.metadata.create_all(engine)
        yield
        observability.shutdown()
        engine.dispose()

    app = FastAPI(
        title="AgentOps MCP Ingestion & Query API",
        version=__version__,
        lifespan=lifespan,
    )
    # CORS: allow the local dashboard dev server in development only.
    # In production, traffic is expected to go through a reverse proxy that
    # serves both the frontend and backend from the same origin.
    if settings.env == "development":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3001", "http://127.0.0.1:3001"],
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.observability = observability
    # None when the diagnostic assistant is not configured (endpoints return 503).
    app.state.diagnostic_provider = build_provider(settings)

    @app.middleware("http")
    async def _ingestion_metrics(request: Request, call_next):
        # Fixed path => bounded `endpoint` label; nothing from the request body.
        if request.method != "POST" or request.url.path != INGEST_ENDPOINT:
            return await call_next(request)
        started = timer()
        try:
            response = await call_next(request)
        except Exception:
            observability.observe_request(INGEST_ENDPOINT, 500, timer() - started)
            raise
        observability.observe_request(INGEST_ENDPOINT, response.status_code, timer() - started)
        return response

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse(exc.body(), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_: Request, exc: RequestValidationError):
        err = ApiError(422, "validation_error", "Request validation failed.",
                       details=_validation_details(exc.errors()))
        return JSONResponse(err.body(), status_code=422)

    @app.exception_handler(ValidationError)
    async def _model_validation(_: Request, exc: ValidationError):
        err = ApiError(422, "validation_error", "Request validation failed.",
                       details=_validation_details(exc.errors()))
        return JSONResponse(err.body(), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        err = ApiError(exc.status_code, code, str(exc.detail))
        return JSONResponse(err.body(), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(SQLAlchemyError)
    async def _db_error(_: Request, exc: SQLAlchemyError):
        logger.error("Database error: %s", type(exc).__name__)
        err = ApiError(503, "database_unavailable", "Storage is temporarily unavailable.")
        return JSONResponse(err.body(), status_code=503)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logger.exception("Unhandled error")
        err = ApiError(500, "internal_error", "An internal error occurred.")
        return JSONResponse(err.body(), status_code=500)

    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(ingest_router)
    app.include_router(query_router)
    app.include_router(admin_router)
    return app


def app_factory() -> FastAPI:  # for `uvicorn agentops_backend.main:app_factory --factory`
    return create_app()


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("agentops_backend.main:app", host="0.0.0.0", port=8000, reload=True)
