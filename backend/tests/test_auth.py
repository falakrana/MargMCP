from __future__ import annotations

from sqlalchemy import create_engine, text

from tests.conftest import (
    ADMIN,
    Tenant,
    admin_headers,
    bearer,
    full_run,
    make_event,
)


# ---- ingestion authentication --------------------------------------------- #
def test_missing_auth_rejected(tenant):
    r = tenant.client.post(
        "/v1/telemetry/events",
        json={"schema_version": "1.0", "project_id": tenant.project_id,
              "batch": [make_event("r", "run_started")]},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"
    assert r.headers["www-authenticate"] == "Bearer"


def test_invalid_keys_rejected(tenant):
    for bad in ["garbage", "aop_deadbeef_notarealsecret", "aop_bad", "Bearer"]:
        r = tenant.send([make_event("r", "run_started")], key=bad)
        assert r.status_code == 401, bad


def test_wrong_scheme_rejected(tenant):
    r = tenant.client.post(
        "/v1/telemetry/events",
        json={"schema_version": "1.0", "project_id": tenant.project_id,
              "batch": [make_event("r", "run_started")]},
        headers={"Authorization": f"Basic {tenant.ingest_key}"},
    )
    assert r.status_code == 401


def test_tampered_key_secret_rejected(tenant):
    r = tenant.send([make_event("r", "run_started")], key=tenant.ingest_key[:-1] + "X")
    assert r.status_code == 401


def test_read_only_key_cannot_ingest(tenant):
    r = tenant.send([make_event("r", "run_started")], key=tenant.read_key)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "insufficient_scope"


def test_ingest_only_key_cannot_read(tenant):
    full_run(tenant, "r")
    r = tenant.get("/runs", key=tenant.ingest_key)
    assert r.status_code == 403


def test_api_key_is_stored_hashed(client, db_path):
    t = Tenant(client)
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT key_hash, key_prefix FROM api_keys")).all()
    assert rows
    for key_hash, prefix in rows:
        assert len(key_hash) == 64
        assert key_hash not in t.ingest_key and t.ingest_key not in key_hash


def test_key_not_logged(client, tenant, caplog):
    with caplog.at_level("DEBUG"):
        tenant.send([make_event("r", "run_started")], key="aop_deadbeef_leakcheck")
        tenant.send([make_event("r", "run_started")])
    assert "leakcheck" not in caplog.text
    assert tenant.ingest_key not in caplog.text


# ---- cross-project isolation ---------------------------------------------- #
def test_cannot_ingest_into_another_project(client):
    a, b = Tenant(client, "a"), Tenant(client, "b")
    r = a.send([make_event("r", "run_started")], project_id=b.project_id)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "project_access_denied"
    assert b.get("/runs").json()["total"] == 0


def test_cannot_read_another_projects_telemetry(client):
    a, b = Tenant(client, "a"), Tenant(client, "b")
    full_run(a, "secret-run")
    full_run(b, "b-run")
    # b's key against a's project path
    for path in ["", "/agents", "/agents/agent-1", "/runs", "/runs/secret-run",
                 "/errors/summary"]:
        r = client.get(
            f"/v1/projects/{a.project_id}{path}", headers=bearer(b.read_key)
        )
        assert r.status_code == 403, path
        assert r.json()["error"]["code"] == "project_access_denied"
        assert "secret-run" not in r.text
    # a's run id is not visible through b's own project either
    assert b.get("/runs/secret-run").status_code == 404
    assert [x["run_id"] for x in b.get("/runs").json()["items"]] == ["b-run"]


def test_revoked_key_rejected(client, db_path):
    t = Tenant(client)
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("UPDATE api_keys SET revoked_at = CURRENT_TIMESTAMP"))
    assert t.send([make_event("r", "run_started")]).status_code == 401


# ---- admin API ------------------------------------------------------------ #
def test_admin_requires_token(client):
    assert client.post("/v1/admin/projects", json={"name": "x"}).status_code == 401
    r = client.post("/v1/admin/projects", json={"name": "x"}, headers=bearer("wrong"))
    assert r.status_code == 401


def test_project_api_key_cannot_use_admin(tenant):
    r = tenant.client.post(
        "/v1/admin/projects", json={"name": "x"}, headers=bearer(tenant.full_key)
    )
    assert r.status_code == 401


def test_admin_disabled_when_token_unset(db_path):
    from fastapi.testclient import TestClient

    from agentops_backend.main import create_app
    from tests.conftest import make_settings

    app = create_app(make_settings(db_path.with_name("noadmin.db"), admin_token=None))
    with TestClient(app) as c:
        r = c.post("/v1/admin/projects", json={"name": "x"}, headers=bearer(ADMIN))
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "admin_disabled"


def test_admin_conflict_and_not_found(client):
    h = admin_headers()
    assert client.post("/v1/admin/projects", json={"name": "x", "project_id": "p1"}, headers=h).status_code == 201
    r = client.post("/v1/admin/projects", json={"name": "x", "project_id": "p1"}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_exists"
    assert client.post("/v1/admin/projects/nope/agents", json={"name": "a"}, headers=h).status_code == 404
    assert client.post("/v1/admin/projects/nope/api-keys", json={"name": "a"}, headers=h).status_code == 404


def test_api_key_response_shows_key_once(client):
    h = admin_headers()
    pid = client.post("/v1/admin/projects", json={"name": "x"}, headers=h).json()["id"]
    created = client.post(f"/v1/admin/projects/{pid}/api-keys", json={"name": "k"}, headers=h).json()
    assert created["api_key"].startswith("aop_")
    # No endpoint ever returns the key again.
    for path in ["", "/agents"]:
        assert created["api_key"] not in client.get(
            f"/v1/projects/{pid}{path}", headers=bearer(created["api_key"])
        ).text


def test_invalid_scope_rejected(client):
    h = admin_headers()
    pid = client.post("/v1/admin/projects", json={"name": "x"}, headers=h).json()["id"]
    r = client.post(f"/v1/admin/projects/{pid}/api-keys",
                    json={"name": "k", "scopes": ["root"]}, headers=h)
    assert r.status_code == 422
