from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from agentops_backend.config import Settings
from agentops_backend.main import create_app

ADMIN = "test-admin-token"
SECRET = "unit-test-secret-key-0123456789abcdef"


def make_settings(db_path, **overrides) -> Settings:
    base = dict(
        database_url=f"sqlite:///{db_path}",
        admin_token=ADMIN,
        secret_key=SECRET,
        auto_create_tables=True,
        env="development",
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def client(db_path):
    app = create_app(make_settings(db_path))
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def admin_headers():
    return {"Authorization": f"Bearer {ADMIN}"}


def bearer(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


class Tenant:
    """A project plus an ingest key and a read key."""

    def __init__(self, client: TestClient, name: str = "p"):
        self.client = client
        r = client.post("/v1/admin/projects", json={"name": name}, headers=admin_headers())
        assert r.status_code == 201, r.text
        self.project_id = r.json()["id"]
        self.ingest_key = self._key(["ingest"])
        self.read_key = self._key(["read"])
        self.full_key = self._key(["ingest", "read"])

    def _key(self, scopes):
        r = self.client.post(
            f"/v1/admin/projects/{self.project_id}/api-keys",
            json={"name": "k", "scopes": scopes},
            headers=admin_headers(),
        )
        assert r.status_code == 201, r.text
        return r.json()["api_key"]

    def send(self, events, key=None, project_id=None, **extra):
        payload = {
            "schema_version": "1.0",
            "project_id": project_id or self.project_id,
            "batch": events,
        }
        payload.update(extra)
        return self.client.post(
            "/v1/telemetry/events", json=payload, headers=bearer(key or self.ingest_key)
        )

    def get(self, path, key=None, **params):
        return self.client.get(
            f"/v1/projects/{self.project_id}{path}",
            headers=bearer(key or self.read_key),
            params=params,
        )


@pytest.fixture
def tenant(client):
    return Tenant(client)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def now() -> datetime:
    return datetime.now(timezone.utc)


def make_event(run_id, event_type, ts=None, agent_id="agent-1", data=None, **kw):
    e = {
        "schema_version": "1.0",
        "event_id": str(uuid.uuid4()),
        "agent_id": agent_id,
        "run_id": run_id,
        "event_type": event_type,
        "timestamp": iso(ts or now()),
        "environment": "production",
        "data": data or {},
    }
    e.update(kw)
    return e


def full_run(tenant, run_id, *, fail=False, start=None, agent_id="agent-1", duration=2):
    start = start or now() - timedelta(minutes=5)
    events = [
        make_event(
            run_id, "run_started", start, agent_id,
            data={"trace_id": uuid.uuid4().hex, "root_span_id": uuid.uuid4().hex[:16]},
        ),
        make_event(
            run_id, "llm_call_completed", start + timedelta(seconds=1), agent_id,
            data={"prompt_tokens": 10, "completion_tokens": 5},
        ),
        make_event(run_id, "tool_call_completed", start + timedelta(seconds=1), agent_id),
    ]
    end = start + timedelta(seconds=duration)
    if fail:
        events.append(
            make_event(run_id, "run_failed", end, agent_id,
                       data={"error_type": "TimeoutError", "error_summary": "timed out"})
        )
    else:
        events.append(make_event(run_id, "run_completed", end, agent_id))
    r = tenant.send(events)
    assert r.status_code == 202, r.text
    return r
