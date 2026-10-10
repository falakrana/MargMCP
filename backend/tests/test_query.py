from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tests.conftest import full_run, iso, make_event, now

BASE = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def seed_timeline(tenant, n=5):
    """n runs, one per minute starting at BASE; timestamps within tolerance are
    required by ingestion, so shift the tolerance via a relative base."""
    anchor = now() - timedelta(hours=2)
    ids = []
    for i in range(n):
        rid = f"run-{i}"
        full_run(tenant, rid, start=anchor + timedelta(minutes=i), fail=(i % 2 == 1),
                 agent_id="alpha" if i < 3 else "beta")
        ids.append(rid)
    return anchor, ids


def test_list_runs_default_order_newest_first(tenant):
    _, ids = seed_timeline(tenant)
    body = tenant.get("/runs").json()
    assert body["total"] == 5
    assert [r["run_id"] for r in body["items"]] == list(reversed(ids))


def test_filter_by_agent_status_environment(tenant):
    seed_timeline(tenant)
    assert tenant.get("/runs", agent_id="alpha").json()["total"] == 3
    assert tenant.get("/runs", agent_id="beta").json()["total"] == 2
    assert tenant.get("/runs", status="error").json()["total"] == 2
    assert tenant.get("/runs", status="success").json()["total"] == 3
    assert tenant.get("/runs", agent_id="alpha", status="error").json()["total"] == 1
    assert tenant.get("/runs", environment="production").json()["total"] == 5
    assert tenant.get("/runs", environment="staging").json()["total"] == 0


def test_invalid_filters_rejected(tenant):
    assert tenant.get("/runs", status="bogus").status_code == 422
    assert tenant.get("/runs", agent_id="bad id!").status_code == 422
    assert tenant.get("/runs", page=0).status_code == 422
    assert tenant.get("/runs", page_size=101).status_code == 422
    assert tenant.get("/runs", started_after="not-a-date").status_code == 422


def test_pagination(tenant):
    _, ids = seed_timeline(tenant)
    seen = []
    for page in (1, 2, 3):
        body = tenant.get("/runs", page=page, page_size=2).json()
        assert body["total"] == 5 and body["page"] == page and body["page_size"] == 2
        seen += [r["run_id"] for r in body["items"]]
    assert seen == list(reversed(ids))
    assert tenant.get("/runs", page=4, page_size=2).json()["items"] == []


def test_time_range_boundaries_are_half_open(tenant):
    anchor, ids = seed_timeline(tenant)
    t2 = iso(anchor + timedelta(minutes=2))
    t4 = iso(anchor + timedelta(minutes=4))
    # started_after is inclusive, started_before is exclusive.
    got = [r["run_id"] for r in tenant.get("/runs", started_after=t2, started_before=t4).json()["items"]]
    assert sorted(got) == ["run-2", "run-3"]
    assert tenant.get("/runs", started_after=t2).json()["total"] == 3
    assert tenant.get("/runs", started_before=t2).json()["total"] == 2
    # a zero-width window is an invalid range (after must be strictly before 'before')
    assert tenant.get("/runs", started_after=t2, started_before=t2).status_code == 422


def test_inverted_time_range_rejected(tenant):
    r = tenant.get("/runs", started_after="2026-02-01T00:00:00Z", started_before="2026-01-01T00:00:00Z")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_time_range"


def test_naive_query_datetime_treated_as_utc(tenant):
    anchor, _ = seed_timeline(tenant)
    naive = (anchor + timedelta(minutes=3)).replace(tzinfo=None).isoformat()
    assert tenant.get("/runs", started_after=naive).json()["total"] == 2


def test_get_run_not_found(tenant):
    r = tenant.get("/runs/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_run_detail_event_cap(tenant):
    full_run(tenant, "r")
    body = tenant.get("/runs/r", max_events=2).json()
    assert len(body["events"]) == 2 and body["event_count"] == 4 and body["events_truncated"]
    assert tenant.get("/runs/r", max_events=0).status_code == 422


def test_run_events_ordered_by_timestamp(tenant):
    t0 = now() - timedelta(minutes=1)
    tenant.send([
        make_event("r", "run_completed", t0 + timedelta(seconds=2)),
        make_event("r", "run_started", t0),
        make_event("r", "tool_call_completed", t0 + timedelta(seconds=1)),
    ])
    types = [e["event_type"] for e in tenant.get("/runs/r").json()["events"]]
    assert types == ["run_started", "tool_call_completed", "run_completed"]


def test_project_and_agent_metadata(tenant):
    seed_timeline(tenant)
    proj = tenant.get("").json()
    assert proj["id"] == tenant.project_id and proj["agent_count"] == 2
    agents = {a["id"]: a for a in tenant.get("/agents").json()}
    assert agents["alpha"]["run_count"] == 3 and agents["beta"]["run_count"] == 2
    assert agents["alpha"]["last_run_at"] is not None
    assert tenant.get("/agents/alpha").json()["run_count"] == 3
    assert tenant.get("/agents/missing").status_code == 404


def test_registered_agent_with_no_runs_listed(tenant):
    from tests.conftest import admin_headers

    tenant.client.post(f"/v1/admin/projects/{tenant.project_id}/agents",
                       json={"name": "idle", "agent_id": "idle"}, headers=admin_headers())
    idle = {a["id"]: a for a in tenant.get("/agents").json()}["idle"]
    assert idle["run_count"] == 0 and idle["last_run_at"] is None


def test_error_summary(tenant):
    seed_timeline(tenant)
    s = tenant.get("/errors/summary").json()
    assert s["total_runs"] == 5 and s["error_runs"] == 2
    assert sum(g["count"] for g in s["groups"]) == 2
    assert {g["error_type"] for g in s["groups"]} == {"TimeoutError"}
    only_alpha = tenant.get("/errors/summary", agent_id="alpha").json()
    assert only_alpha["error_runs"] == 1 and only_alpha["total_runs"] == 3


def test_error_summary_time_range(tenant):
    anchor, _ = seed_timeline(tenant)
    s = tenant.get("/errors/summary", started_after=iso(anchor + timedelta(minutes=2))).json()
    assert s["total_runs"] == 3 and s["error_runs"] == 1


def test_run_metadata_exposed(tenant):
    t0 = now() - timedelta(minutes=1)
    tenant.send([make_event("r", "run_started", t0, data={"metadata": {"team": "ml"}})])
    assert tenant.get("/runs/r").json()["run"]["metadata"] == {"team": "ml"}
