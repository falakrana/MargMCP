from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import OperationalError

from marg_backend import ingestion
from marg_backend.config import Settings
from marg_backend.main import create_app
from marg_backend.models import Base
from tests.conftest import Tenant, full_run, make_event, make_settings


def test_database_error_during_ingestion_rolls_back_whole_batch(client, tenant, monkeypatch):
    original = ingestion._process_event
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OperationalError("INSERT", {}, Exception("db went away"))
        return original(*args, **kwargs)

    monkeypatch.setattr(ingestion, "_process_event", flaky)
    r = tenant.send([make_event("r", "run_started"), make_event("r", "run_completed")])
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "database_unavailable"
    assert "db went away" not in r.text  # no driver details leaked
    monkeypatch.setattr(ingestion, "_process_event", original)
    # Atomic: the first event of the failed batch was rolled back.
    assert tenant.get("/runs/r").status_code == 404
    # A retry of the same batch succeeds in full.
    assert tenant.send([make_event("r", "run_started")]).json()["accepted"] == 1


def test_database_unreachable_returns_structured_503(db_path, tenant, client):
    # Point the live app at an engine that cannot open its database.
    broken = create_engine("sqlite:////nonexistent-dir-xyz/none.db")
    from marg_backend.db import make_session_factory

    client.app.state.session_factory = make_session_factory(broken)
    r = client.get(f"/v1/projects/{tenant.project_id}/runs",
                   headers={"Authorization": f"Bearer {tenant.read_key}"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "database_unavailable"
    assert "nonexistent" not in r.text


def test_query_database_error_is_503(client, tenant, monkeypatch):
    from marg_backend import queries

    def boom(*a, **k):
        raise OperationalError("SELECT", {}, Exception("secret dsn"))

    monkeypatch.setattr(queries, "list_runs", boom)
    r = tenant.get("/runs")
    assert r.status_code == 503 and "secret dsn" not in r.text


def test_unexpected_error_hides_internals(client, tenant, monkeypatch):
    from marg_backend import queries

    monkeypatch.setattr(queries, "get_project", lambda *a, **k: 1 / 0)
    r = tenant.get("")
    assert r.status_code == 500
    assert r.json() == {"error": {"code": "internal_error", "message": "An internal error occurred."}}


def test_data_survives_service_restart(db_path):
    settings = make_settings(db_path)
    with TestClient(create_app(settings)) as c1:
        t = Tenant(c1)
        full_run(t, "persisted")
        project_id, key = t.project_id, t.read_key
    # New app instance = restarted service, same database file.
    with TestClient(create_app(settings)) as c2:
        r = c2.get(f"/v1/projects/{project_id}/runs/persisted",
                   headers={"Authorization": f"Bearer {key}"})
        assert r.status_code == 200
        assert r.json()["run"]["status"] == "success"
        assert r.json()["event_count"] == 4


def test_health_live_and_ready(client):
    assert client.get("/health/live").json() == {"status": "alive"}
    r = client.get("/health/ready")
    assert r.status_code == 200 and r.json() == {"status": "ready"}


def test_health_does_not_require_auth_and_leaks_nothing(client):
    text = client.get("/health/ready").text + client.get("/health/live").text
    for needle in ("sqlite", "password", "secret", "postgres"):
        assert needle not in text.lower()


def test_readiness_503_when_db_down_without_details(client):
    from marg_backend.db import make_session_factory

    client.app.state.session_factory = make_session_factory(
        create_engine("sqlite:////nonexistent-dir-xyz/none.db")
    )
    r = client.get("/health/ready")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "not_ready"
    assert "nonexistent" not in r.text


def test_insecure_secret_rejected_outside_development():
    with pytest.raises(RuntimeError):
        create_app(Settings(_env_file=None, env="production",
                            database_url="sqlite://", secret_key="change-me-to-a-random-string"))
    with pytest.raises(RuntimeError):
        create_app(Settings(_env_file=None, env="staging", database_url="sqlite://",
                            secret_key="short"))


def test_postgres_url_assembled_from_env_parts():
    s = Settings(_env_file=None, POSTGRES_HOST="db", POSTGRES_PORT=5433, POSTGRES_DB="d",
                 POSTGRES_USER="u@x", POSTGRES_PASSWORD="p w")
    assert s.resolved_database_url() == "postgresql+psycopg://u%40x:p+w@db:5433/d"


def test_alembic_migration_matches_models(tmp_path):
    """The migration must create the same tables/indexes as the ORM models."""
    from alembic import command
    from alembic.config import Config
    import pathlib

    backend = pathlib.Path(__file__).resolve().parents[1]
    url = f"sqlite:///{tmp_path / 'mig.db'}"
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    migrated = inspect(create_engine(url))
    model_engine = create_engine(f"sqlite:///{tmp_path / 'model.db'}")
    Base.metadata.create_all(model_engine)
    modeled = inspect(model_engine)

    tables = set(Base.metadata.tables)
    assert tables <= set(migrated.get_table_names())
    for table in tables:
        mig_cols = {c["name"] for c in migrated.get_columns(table)}
        mod_cols = {c["name"] for c in modeled.get_columns(table)}
        assert mig_cols == mod_cols, table
        mig_idx = {i["name"] for i in migrated.get_indexes(table)}
        mod_idx = {i["name"] for i in modeled.get_indexes(table)}
        assert mig_idx == mod_idx, table
    command.downgrade(cfg, "base")
    assert not (tables & set(inspect(create_engine(url)).get_table_names()))
