"""Database engine and session helpers."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from marg_backend.config import Settings


def make_engine(url: str, settings: Optional[Settings] = None) -> Engine:
    """Create the engine.

    For server databases the pool is bounded and fails fast: a saturated pool
    raises after ``db_pool_timeout_seconds`` (surfaced as a structured 503)
    instead of queueing requests indefinitely, and connections are recycled
    before typical idle-timeout limits. ``settings=None`` keeps library defaults
    (used by Alembic and tests).
    """
    if not url.startswith("sqlite"):
        if settings is None:
            return create_engine(url, pool_pre_ping=True)
        kwargs: dict = dict(
            pool_pre_ping=True,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout_seconds,
            pool_recycle=settings.db_pool_recycle_seconds,
        )
        if url.startswith("postgresql"):
            kwargs["connect_args"] = {"connect_timeout": settings.db_connect_timeout_seconds}
        engine = create_engine(url, **kwargs)
        timeout_ms = settings.db_statement_timeout_ms
        if timeout_ms is not None and url.startswith("postgresql"):

            @event.listens_for(engine, "connect")
            def _statement_timeout(dbapi_connection, _record):
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute(f"SET statement_timeout = {int(timeout_ms)}")
                finally:
                    cursor.close()

        return engine

    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _disable_pysqlite_autobegin(dbapi_connection, _record):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _emit_begin(conn):
        conn.exec_driver_sql("BEGIN")

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=True)
