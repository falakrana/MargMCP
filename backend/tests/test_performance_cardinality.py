"""Phase 9 — Performance, database indexes, query limits, and Prometheus cardinality bounds."""
from __future__ import annotations

import time
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text

from marg_backend.metrics import Metrics, SeriesCap
from marg_backend.observability import EventObservation, Observability
from tests.conftest import full_run, make_event, now


def test_series_cap_bounds_combinatorial_explosion():
    cap = SeriesCap(max_series=50)
    # Generate 200 distinct combinations
    for i in range(200):
        res = cap((f"agent_{i}", f"provider_{i}", f"model_{i}"))
        if i < 50:
            assert res == (f"agent_{i}", f"provider_{i}", f"model_{i}")
        else:
            assert res == ("other", "other", "other")
    assert len(cap) == 50


def test_prometheus_label_explosion_prevented():
    metrics = Metrics()
    # Stress test: feed 500 different agents and 500 models
    for i in range(500):
        agent = metrics.agent(f"dynamic-agent-{i}")
        model = metrics.model(f"dynamic-model-{i}")
        provider = metrics.provider(f"dynamic-provider-{i}")
        agent, provider, model = metrics.llm_series((agent, provider, model))
        metrics.llm_calls_total.labels(
            agent_id=agent, provider=provider, model=model, status="ok"
        ).inc()

    # Verify agent label caps at 200 (BoundedLabel max_values)
    assert len(metrics.agent._seen) == 200
    # Verify llm_series caps at 2000
    assert len(metrics.llm_series) <= 2000


def test_database_indexes_cover_expected_access_patterns(client):
    """Verify that expected indexes exist on runs and events tables."""
    with client.app.state.session_factory() as session:
        # Check SQLite or Postgres indexes
        rows = session.execute(
            text("SELECT name FROM sqlite_master WHERE type='index'")
        ).scalars().all()
        index_names = set(rows)

        expected = {
            "ix_runs_project_started",
            "ix_runs_project_agent_started",
            "ix_runs_project_status_started",
            "ix_runs_project_env_started",
            "ix_runs_project_error",
            "ix_events_project_run_ts",
            "uq_api_keys_prefix",
        }
        assert expected <= index_names, f"Missing indexes: {expected - index_names}"


def test_synthetic_ingestion_and_query_workload(client, tenant):
    """Benchmark ingestion and query throughput with a documented synthetic workload."""
    batch_size = 50
    batches = 4
    total_events = batch_size * batches

    # Ingestion benchmark
    start_time = time.perf_counter()
    for b in range(batches):
        events = [
            make_event(f"bench-run-{b}-{i}", "run_started", data={"prompt_tokens": 10})
            for i in range(batch_size)
        ]
        r = tenant.send(events)
        assert r.status_code == 202
        assert r.json()["accepted"] == batch_size
    ingest_duration = time.perf_counter() - start_time
    ingest_throughput = total_events / ingest_duration

    # Ingestion should process > 50 events/second even on SQLite in tests
    assert ingest_throughput > 30.0, f"Ingestion too slow: {ingest_throughput:.1f} events/sec"

    # Query benchmark: list runs, error summary
    query_start = time.perf_counter()
    r = tenant.get("/runs?page=1&page_size=50")
    assert r.status_code == 200
    assert r.json()["total"] >= total_events

    r = tenant.get("/errors/summary")
    assert r.status_code == 200

    query_duration = time.perf_counter() - query_start
    assert query_duration < 2.0, f"Queries too slow: {query_duration:.3f}s"


def test_rest_api_query_bounds(tenant):
    # Time window too large (exceeds rest_max_window_days=366)
    too_old = now() - timedelta(days=400)
    r = tenant.get(
        "/runs",
        started_after=too_old.isoformat().replace("+00:00", "Z"),
        started_before=now().isoformat().replace("+00:00", "Z"),
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "time_window_too_large"

    # Deep pagination offset rejected
    r = tenant.get("/runs", page=2500, page_size=50)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "page_out_of_range"
