from __future__ import annotations

from fastapi.testclient import TestClient

from marg_backend import config, seed
from marg_backend.main import create_app
from tests.conftest import make_settings


def test_seed_creates_labelled_synthetic_data(db_path, monkeypatch):
    monkeypatch.setenv("AGENTOPS_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("AGENTOPS_SECRET_KEY", "unit-test-secret-key-0123456789abcdef")
    config.get_settings.cache_clear()
    try:
        key = seed.seed(run_count=12)
        assert key.startswith("aop_")
        # Idempotent re-run (project/agents already exist) must not fail.
        seed.seed(run_count=3)
    finally:
        config.get_settings.cache_clear()

    settings = make_settings(db_path, secret_key="unit-test-secret-key-0123456789abcdef")
    with TestClient(create_app(settings)) as c:
        h = {"Authorization": f"Bearer {key}"}
        proj = c.get(f"/v1/projects/{seed.DEMO_PROJECT_ID}", headers=h).json()
        assert "SYNTHETIC" in proj["name"]
        runs = c.get(f"/v1/projects/{seed.DEMO_PROJECT_ID}/runs?page_size=100", headers=h).json()
        assert runs["total"] >= 12
        assert all(r["run_id"].startswith("synthetic-") for r in runs["items"])
        assert all(r["metadata"] == {"synthetic": "true"} for r in runs["items"])
        agents = c.get(f"/v1/projects/{seed.DEMO_PROJECT_ID}/agents", headers=h).json()
        assert all(a["id"].startswith("synthetic-") for a in agents)
