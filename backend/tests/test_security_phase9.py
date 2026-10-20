"""Phase 9 — Security hardening tests: secret scrubbing, rate limiting, body caps,

security headers, API key rotation, and retention purge.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from agentops_backend.auth import hash_key, safe_equals
from agentops_backend.config import Settings
from agentops_backend.logging_config import JsonFormatter, install_scrubbing
from agentops_backend.main import create_app
from agentops_backend.redact import scrub_obj, scrub_text
from agentops_backend.security import RateLimiter, client_ip
from tests.conftest import (
    ADMIN,
    Tenant,
    admin_headers,
    bearer,
    full_run,
    make_event,
    make_settings,
    now,
)


def test_safe_equals():
    assert safe_equals("hello", "hello")
    assert not safe_equals("hello", "world")
    # Must not raise on non-ASCII or surrogate characters
    assert safe_equals("café 🚀", "café 🚀")
    assert not safe_equals("café 🚀", "cafe")


def test_secret_scrubbing_patterns():
    # API keys
    assert "aop_[REDACTED]" in scrub_text("key: aop_12345678_abcdefghijklmnopqrstuvwxyz")
    # Bearer tokens
    assert "Bearer [REDACTED]" in scrub_text("Authorization: Bearer secret-token-xyz-123456")
    # sk/gsk keys
    assert "[REDACTED_KEY]" in scrub_text("my key is sk-1234567890abcdef123456")
    assert "[REDACTED_KEY]" in scrub_text("my key is gsk-1234567890abcdef123456")
    # JWTs
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozG4sEGsr_Fv_Wn_H1J"
    assert "[REDACTED_JWT]" in scrub_text(f"token={jwt}")
    # URL credentials
    url = "postgresql://user:super_secret_pw@db.example.com:5432/agentops"
    assert "user:super_secret_pw" not in scrub_text(url)
    assert "postgresql://[REDACTED]@db.example.com:5432/agentops" in scrub_text(url)
    # Generic key-value patterns
    assert "password: [REDACTED]" in scrub_text("password: mypassword123")
    assert 'client_secret="[REDACTED]"' in scrub_text('client_secret="mysecret"')


def test_scrub_obj_recursive():
    payload = {
        "user": "alice",
        "api_key": "raw-key-123",
        "nested": {
            "token": "token-xyz",
            "safe_field": "safe",
            "inner_list": [
                {"password": "secret", "url": "https://user:pass@host.com/path"}
            ]
        }
    }
    scrubbed = scrub_obj(payload)
    assert scrubbed["user"] == "alice"
    assert scrubbed["api_key"] == "[REDACTED]"
    assert scrubbed["nested"]["token"] == "[REDACTED]"
    assert scrubbed["nested"]["safe_field"] == "safe"
    assert scrubbed["nested"]["inner_list"][0]["password"] == "[REDACTED]"
    assert "pass@" not in scrubbed["nested"]["inner_list"][0]["url"]


def test_json_log_formatter_scrubs_secrets():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Connected to postgresql://admin:secret123@localhost:5432/db with token sk-abcdef1234567890",
        args=(),
        exc_info=None,
    )
    formatted = formatter.format(record)
    parsed = json.loads(formatted)
    assert "secret123" not in parsed["message"]
    assert "sk-abcdef1234567890" not in parsed["message"]
    assert "[REDACTED]" in parsed["message"]
    assert parsed["level"] == "INFO"
    assert "ts" in parsed


def test_security_headers_present(client):
    r = client.get("/health/live")
    assert r.status_code == 200
    assert "X-Request-ID" in r.headers
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert r.headers["Cache-Control"] == "no-store"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]


def test_rate_limiter_fixed_window():
    limiter = RateLimiter(max_keys=100, window_seconds=60.0)
    for _ in range(5):
        allowed, retry_after = limiter.hit("test", "user1", limit=5)
        assert allowed
    # 6th hit exceeds limit of 5
    allowed, retry_after = limiter.hit("test", "user1", limit=5)
    assert not allowed
    assert retry_after > 0


def test_rate_limit_ip_flood(db_path):
    settings = make_settings(
        db_path,
        rate_limit_enabled=True,
        rate_limit_ip_per_minute=5,
    )
    app = create_app(settings)
    with TestClient(app) as c:
        for _ in range(5):
            r = c.get("/v1/projects/any-project", headers=admin_headers())
            assert r.status_code in (200, 401, 403, 404)
        # 6th call from same client IP triggers 429
        r = c.get("/v1/projects/any-project", headers=admin_headers())
        assert r.status_code == 429
        assert r.json()["error"]["code"] == "rate_limited"
        assert "Retry-After" in r.headers


def test_rate_limit_auth_failures_throttle(db_path, tenant):
    settings = make_settings(
        db_path,
        rate_limit_enabled=True,
        rate_limit_auth_failures_per_minute=3,
    )
    app = create_app(settings)
    with TestClient(app) as c:
        # Send invalid tokens
        for _ in range(3):
            r = c.get(f"/v1/projects/{tenant.project_id}/runs", headers=bearer("invalid-token"))
            assert r.status_code == 401
        # Subsequent requests from this IP get 429
        r = c.get(f"/v1/projects/{tenant.project_id}/runs", headers=bearer("invalid-token"))
        assert r.status_code == 429
        assert r.json()["error"]["code"] == "rate_limited"


def test_body_limit_middleware_rejects_oversized_payload(db_path, tenant):
    settings = make_settings(db_path, max_payload_bytes=1024)
    app = create_app(settings)
    with TestClient(app) as c:
        # Huge body
        big_data = {"key": "x" * 2000}
        r = c.post(
            "/v1/telemetry/events",
            json={"schema_version": "1.0", "project_id": tenant.project_id, "batch": [make_event("r", "run_started", data=big_data)]},
            headers=bearer(tenant.ingest_key),
        )
        assert r.status_code == 413
        assert r.json()["error"]["code"] == "payload_too_large"


def test_docs_disabled_in_production(db_path):
    settings = make_settings(
        db_path,
        env="production",
        secret_key="unit-test-secret-key-0123456789abcdef",
        admin_token="admin-token-0123456789abcdef",
        metrics_token="metrics-token-0123456789abcdef",
    )
    app = create_app(settings)
    with TestClient(app) as c:
        assert c.get("/docs").status_code == 404
        assert c.get("/redoc").status_code == 404
        assert c.get("/openapi.json").status_code == 404


def test_api_key_lifecycle_list_revoke_rotate(client, tenant):
    # 1. Create a key
    r = client.post(
        f"/v1/admin/projects/{tenant.project_id}/api-keys",
        json={"name": "worker-key", "scopes": ["ingest"]},
        headers=admin_headers(),
    )
    assert r.status_code == 201
    created = r.json()
    key_id = created["id"]
    api_key = created["api_key"]

    # Key works for ingestion
    ev = [make_event("r1", "run_started")]
    r = tenant.send(ev, key=api_key)
    assert r.status_code == 202

    # 2. List keys: prefix is shown, raw key is NEVER returned
    r = client.get(f"/v1/admin/projects/{tenant.project_id}/api-keys", headers=admin_headers())
    assert r.status_code == 200
    keys = r.json()
    assert any(k["id"] == key_id for k in keys)
    for k in keys:
        assert "api_key" not in k
        assert "key_hash" not in k
        assert len(k["key_prefix"]) == 8

    # 3. Rotate key (with revoke_old=True)
    r = client.post(
        f"/v1/admin/projects/{tenant.project_id}/api-keys/{key_id}/rotate",
        json={"revoke_old": True},
        headers=admin_headers(),
    )
    assert r.status_code == 200
    rotated = r.json()
    new_api_key = rotated["new_key"]["api_key"]
    assert rotated["old_key"]["revoked_at"] is not None

    # Old key fails with 401
    r = tenant.send([make_event("r2", "run_started")], key=api_key)
    assert r.status_code == 401

    # New key succeeds
    r = tenant.send([make_event("r2", "run_started")], key=new_api_key)
    assert r.status_code == 202

    # 4. Revoke the new key explicitly
    new_key_id = rotated["new_key"]["id"]
    r = client.post(
        f"/v1/admin/projects/{tenant.project_id}/api-keys/{new_key_id}/revoke",
        headers=admin_headers(),
    )
    assert r.status_code == 200
    assert r.json()["active"] is False

    # Now new key also fails
    r = tenant.send([make_event("r3", "run_started")], key=new_api_key)
    assert r.status_code == 401


def test_retention_purge_dry_run_and_execution(client, tenant):
    # Seed 3 runs: 2 old, 1 fresh
    full_run(tenant, "old-run-1")
    full_run(tenant, "old-run-2")
    full_run(tenant, "fresh-run-1")
    old_time = now() - timedelta(days=40)
    with client.app.state.session_factory() as s:
        from sqlalchemy import update
        from agentops_backend.models import Run
        s.execute(
            update(Run)
            .where(Run.run_id.in_(["old-run-1", "old-run-2"]))
            .values(started_at=old_time)
        )
        s.commit()

    # Dry run purge for older_than_days=30
    r = client.post(
        "/v1/admin/retention/purge",
        json={"older_than_days": 30, "dry_run": True},
        headers=admin_headers(),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["dry_run"] is True
    assert data["runs"] == 2
    assert data["events"] > 0

    # Old runs still exist
    assert tenant.get("/runs/old-run-1").status_code == 200

    # Execute purge
    r = client.post(
        "/v1/admin/retention/purge",
        json={"older_than_days": 30, "dry_run": False},
        headers=admin_headers(),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["dry_run"] is False
    assert data["runs"] == 2

    # Old runs are gone (404)
    assert tenant.get("/runs/old-run-1").status_code == 404
    assert tenant.get("/runs/old-run-2").status_code == 404

    # Fresh run remains
    assert tenant.get("/runs/fresh-run-1").status_code == 200


def test_delete_project_telemetry(client, tenant):
    full_run(tenant, "run-to-purge-1")
    full_run(tenant, "run-to-purge-2")

    # Dry run
    r = client.delete(
        f"/v1/admin/projects/{tenant.project_id}/telemetry?dry_run=true",
        headers=admin_headers(),
    )
    assert r.status_code == 200
    assert r.json()["runs"] == 2
    assert tenant.get("/runs/run-to-purge-1").status_code == 200

    # Execute project purge
    r = client.delete(
        f"/v1/admin/projects/{tenant.project_id}/telemetry?dry_run=false",
        headers=admin_headers(),
    )
    assert r.status_code == 200
    assert r.json()["runs"] == 2
    assert tenant.get("/runs/run-to-purge-1").status_code == 404
    assert tenant.get("/runs/run-to-purge-2").status_code == 404
