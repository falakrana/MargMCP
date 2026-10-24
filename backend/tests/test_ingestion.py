from __future__ import annotations

import uuid
from datetime import timedelta

from tests.conftest import full_run, iso, make_event, now


def codes(resp):
    return [r["code"] for r in resp.json()["rejected"]]


def test_valid_run_is_persisted_and_retrievable(tenant):
    full_run(tenant, "run-1")
    r = tenant.get("/runs/run-1")
    assert r.status_code == 200
    body = r.json()
    run = body["run"]
    assert run["status"] == "success"
    assert run["llm_call_count"] == 1 and run["tool_call_count"] == 1
    assert run["total_tokens"] == 15
    assert run["duration_ms"] == 2000
    assert len(run["trace_id"]) == 32 and len(run["root_span_id"]) == 16
    assert body["event_count"] == 4 and not body["events_truncated"]
    types = [e["event_type"] for e in body["events"]]
    assert types[0] == "run_started" and types[-1] == "run_completed"


def test_failed_run_records_error(tenant):
    full_run(tenant, "run-f", fail=True)
    run = tenant.get("/runs/run-f").json()["run"]
    assert run["status"] == "error"
    assert run["error_type"] == "TimeoutError"
    assert run["error_summary"] == "timed out"


def test_ingestion_returns_202_with_counts(tenant):
    evs = [make_event("r", "run_started"), make_event("r", "run_completed")]
    r = tenant.send(evs)
    assert r.status_code == 202
    assert r.json() == {"accepted": 2, "duplicates": 0, "rejected": []}


# ---- schema / envelope validation --------------------------------------- #
def test_unsupported_schema_version(tenant):
    r = tenant.send([make_event("r", "run_started")], schema_version="2.0")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "unsupported_schema_version"


def test_missing_schema_version(tenant):
    payload = {"project_id": tenant.project_id, "batch": [make_event("r", "run_started")]}
    r = tenant.client.post(
        "/v1/telemetry/events", json=payload,
        headers={"Authorization": f"Bearer {tenant.ingest_key}"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "unsupported_schema_version"


def test_invalid_json_body(tenant):
    r = tenant.client.post(
        "/v1/telemetry/events", content=b"{not json",
        headers={"Authorization": f"Bearer {tenant.ingest_key}"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_json"


def test_body_must_be_object(tenant):
    r = tenant.client.post(
        "/v1/telemetry/events", json=[1, 2],
        headers={"Authorization": f"Bearer {tenant.ingest_key}"},
    )
    assert r.status_code == 422


def test_structured_validation_error_does_not_echo_input(tenant):
    bad = make_event("r", "run_started")
    bad["event_id"] = "bad id with spaces <script>"
    r = tenant.send([bad])
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert "<script>" not in r.text
    assert any("event_id" in d["loc"] for d in err["details"])


def test_unknown_event_type_rejected(tenant):
    r = tenant.send([make_event("r", "totally_made_up")])
    assert r.status_code == 422


def test_unknown_event_field_rejected(tenant):
    r = tenant.send([make_event("r", "run_started", sneaky="x")])
    assert r.status_code == 422


def test_empty_batch_rejected(tenant):
    assert tenant.send([]).status_code == 422


def test_batch_too_large(tenant):
    evs = [make_event("r", "custom_event") for _ in range(101)]
    r = tenant.send(evs)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "batch_too_large"


def test_max_batch_accepted(tenant):
    evs = [make_event("r", "custom_event") for _ in range(100)]
    r = tenant.send(evs)
    assert r.status_code == 202 and r.json()["accepted"] == 100


def test_payload_size_limit(client, db_path):
    from fastapi.testclient import TestClient

    from marg_backend.main import create_app
    from tests.conftest import Tenant, make_settings

    app = create_app(make_settings(db_path.with_name("small.db"), max_payload_bytes=2048))
    with TestClient(app) as c:
        t = Tenant(c)
        big = make_event("r", "custom_event", data={"summary": "x" * 5000})
        r = t.send([big])
        assert r.status_code == 413
        assert r.json()["error"]["code"] == "payload_too_large"


def test_event_data_size_limit(tenant):
    big = make_event("r", "custom_event", data={"summary": {"k": "x" * 20000}})
    r = tenant.send([big])
    assert r.status_code == 202
    assert codes(r) == ["data_too_large"]


# ---- timestamps ----------------------------------------------------------- #
def test_malformed_timestamp(tenant):
    bad = make_event("r", "run_started")
    bad["timestamp"] = "yesterday-ish"
    assert tenant.send([bad]).status_code == 422


def test_numeric_timestamp_rejected(tenant):
    bad = make_event("r", "run_started")
    bad["timestamp"] = 1759900000
    assert tenant.send([bad]).status_code == 422


def test_naive_timestamp_rejected(tenant):
    bad = make_event("r", "run_started")
    bad["timestamp"] = "2026-10-04T05:30:00"
    assert tenant.send([bad]).status_code == 422


def test_timestamp_offsets_normalized_to_utc(tenant):
    from datetime import datetime, timezone

    instant = datetime.now(timezone.utc).replace(microsecond=0)
    ist = timezone(timedelta(hours=5, minutes=30))
    e = make_event("r-tz", "run_started")
    e["timestamp"] = instant.astimezone(ist).isoformat()  # e.g. ...+05:30
    assert e["timestamp"].endswith("+05:30")
    assert tenant.send([e]).status_code == 202
    started = tenant.get("/runs/r-tz").json()["run"]["started_at"]
    assert datetime.fromisoformat(started.replace("Z", "+00:00")) == instant
    assert started.endswith("Z") or started.endswith("+00:00")


def test_timestamp_outside_tolerance_rejected_per_event(tenant):
    old = make_event("r", "run_started", now() - timedelta(hours=25))
    future = make_event("r2", "run_started", now() + timedelta(hours=25))
    ok = make_event("r3", "run_started", now() - timedelta(hours=23))
    r = tenant.send([old, future, ok])
    assert r.status_code == 202
    body = r.json()
    assert body["accepted"] == 1
    assert [x["code"] for x in body["rejected"]] == ["timestamp_out_of_range"] * 2
    assert [x["index"] for x in body["rejected"]] == [0, 1]


# ---- attribute rules ------------------------------------------------------ #
def test_forbidden_attributes_rejected(tenant):
    r = tenant.send([make_event("r", "llm_call_completed", data={"prompt": "secret user text"})])
    assert codes(r) == ["forbidden_attribute"]
    assert tenant.get("/runs/r").status_code == 404  # nothing stored


def test_forbidden_nested_attribute_key(tenant):
    r = tenant.send(
        [make_event("r", "custom_event", data={"attributes": {"llm.prompt": "x"}})]
    )
    assert codes(r) == ["forbidden_attribute"]


def test_unknown_data_keys_are_dropped_not_stored(tenant):
    tenant.send([make_event("r", "custom_event", data={"zzz_unknown": "v", "model": "m"})])
    ev = tenant.get("/runs/r").json()["events"][0]
    assert ev["data"] == {"model": "m"}


def test_metadata_limits(tenant):
    too_many = {f"k{i}": "v" for i in range(11)}
    long_val = {"k": "v" * 257}
    r = tenant.send([
        make_event("a", "run_started", data={"metadata": too_many}),
        make_event("b", "run_started", data={"metadata": long_val}),
        make_event("c", "run_started", data={"metadata": {"team": "ml"}}),
    ])
    assert codes(r) == ["invalid_metadata", "invalid_metadata"]
    assert r.json()["accepted"] == 1


def test_invalid_trace_and_token_values(tenant):
    r = tenant.send([
        make_event("a", "run_started", data={"trace_id": "nothex"}),
        make_event("b", "llm_call_completed", data={"prompt_tokens": -1}),
        make_event("c", "llm_call_completed", data={"prompt_tokens": True}),
    ])
    assert codes(r) == ["invalid_trace_id", "invalid_token_count", "invalid_token_count"]


def test_error_summary_truncated(tenant):
    tenant.send([
        make_event("r", "run_started"),
        make_event("r", "run_failed", data={"error_type": "E", "error_summary": "x" * 5000}),
    ])
    assert len(tenant.get("/runs/r").json()["run"]["error_summary"]) == 1024


# ---- idempotency ---------------------------------------------------------- #
def test_duplicate_events_do_not_corrupt_history(tenant):
    start = now() - timedelta(minutes=1)
    evs = [
        make_event("r", "run_started", start),
        make_event("r", "llm_call_completed", start, data={"prompt_tokens": 7, "completion_tokens": 3}),
        make_event("r", "run_completed", start + timedelta(seconds=1)),
    ]
    first = tenant.send(evs)
    again = tenant.send(evs)
    assert first.json()["accepted"] == 3
    assert again.status_code == 202
    assert again.json() == {"accepted": 0, "duplicates": 3, "rejected": []}
    body = tenant.get("/runs/r").json()
    assert body["event_count"] == 3
    assert body["run"]["llm_call_count"] == 1
    assert body["run"]["total_tokens"] == 10


def test_duplicate_within_same_batch(tenant):
    e = make_event("r", "llm_call_completed", data={"prompt_tokens": 1})
    r = tenant.send([e, e])
    assert r.json()["accepted"] == 1 and r.json()["duplicates"] == 1
    assert tenant.get("/runs/r").json()["run"]["llm_call_count"] == 1


def test_duplicate_retry_after_tolerance_window_is_still_duplicate(tenant):
    e = make_event("r", "run_started")
    tenant.send([e])
    r = tenant.send([e])
    assert r.json()["duplicates"] == 1


# ---- out-of-order & lifecycle -------------------------------------------- #
def test_out_of_order_events_converge(tenant):
    start = now() - timedelta(minutes=2)
    started = make_event("r", "run_started", start,
                         data={"trace_id": "a" * 32, "root_span_id": "b" * 16})
    llm = make_event("r", "llm_call_completed", start + timedelta(seconds=1),
                     data={"prompt_tokens": 4, "completion_tokens": 1})
    done = make_event("r", "run_completed", start + timedelta(seconds=3))

    assert tenant.send([done]).status_code == 202
    run = tenant.get("/runs/r").json()["run"]
    assert run["status"] == "success" and run["duration_ms"] is None

    tenant.send([llm])
    tenant.send([started])
    run = tenant.get("/runs/r").json()["run"]
    assert run["status"] == "success"
    assert run["trace_id"] == "a" * 32 and run["root_span_id"] == "b" * 16
    assert run["duration_ms"] == 3000
    assert run["total_tokens"] == 5


def test_placeholder_run_is_unknown_until_started(tenant):
    tenant.send([make_event("r", "llm_call_completed")])
    assert tenant.get("/runs/r").json()["run"]["status"] == "unknown"
    tenant.send([make_event("r", "run_started")])
    assert tenant.get("/runs/r").json()["run"]["status"] == "running"


def test_conflicting_terminal_transition_rejected(tenant):
    t0 = now() - timedelta(minutes=1)
    tenant.send([make_event("r", "run_started", t0), make_event("r", "run_completed", t0)])
    r = tenant.send([make_event("r", "run_failed", t0, data={"error_type": "X"})])
    assert codes(r) == ["invalid_status_transition"]
    run = tenant.get("/runs/r").json()["run"]
    assert run["status"] == "success" and run["error_type"] is None


def test_same_terminal_status_repeat_is_idempotent(tenant):
    t0 = now() - timedelta(minutes=1)
    tenant.send([make_event("r", "run_started", t0), make_event("r", "run_completed", t0)])
    r = tenant.send([make_event("r", "run_completed", t0 + timedelta(seconds=9))])
    assert r.json()["accepted"] == 1 and r.json()["rejected"] == []
    assert tenant.get("/runs/r").json()["run"]["duration_ms"] == 0


def test_late_events_after_terminal_still_recorded(tenant):
    t0 = now() - timedelta(minutes=1)
    tenant.send([make_event("r", "run_started", t0), make_event("r", "run_completed", t0)])
    tenant.send([make_event("r", "tool_call_completed", t0)])
    assert tenant.get("/runs/r").json()["run"]["tool_call_count"] == 1


def test_agent_mismatch_for_existing_run_rejected(tenant):
    tenant.send([make_event("r", "run_started", agent_id="a1")])
    r = tenant.send([make_event("r", "custom_event", agent_id="a2")])
    assert codes(r) == ["agent_mismatch"]


def test_cancelled_run(tenant):
    t0 = now() - timedelta(minutes=1)
    tenant.send([make_event("r", "run_started", t0), make_event("r", "run_cancelled", t0)])
    assert tenant.get("/runs/r").json()["run"]["status"] == "cancelled"


def test_agent_is_auto_registered(tenant):
    tenant.send([make_event("r", "run_started", agent_id="new-agent")])
    agent = tenant.get("/agents/new-agent").json()
    assert agent["auto_registered"] is True and agent["run_count"] == 1


def test_unregistered_agent_rejected_when_auto_register_off(db_path):
    from fastapi.testclient import TestClient

    from marg_backend.main import create_app
    from tests.conftest import Tenant, admin_headers, make_settings

    app = create_app(make_settings(db_path.with_name("strict.db"), auto_register_agents=False))
    with TestClient(app) as c:
        t = Tenant(c)
        r = t.send([make_event("r", "run_started", agent_id="ghost")])
        assert codes(r) == ["unknown_agent"]
        c.post(f"/v1/admin/projects/{t.project_id}/agents",
               json={"name": "ghost", "agent_id": "ghost"}, headers=admin_headers())
        assert t.send([make_event("r", "run_started", agent_id="ghost")]).json()["accepted"] == 1


def test_run_id_reuse_across_projects_is_isolated(client):
    from tests.conftest import Tenant

    a, b = Tenant(client, "a"), Tenant(client, "b")
    shared = "shared-run"
    t0 = now() - timedelta(minutes=1)
    a.send([make_event(shared, "run_started", t0), make_event(shared, "run_completed", t0)])
    b.send([make_event(shared, "run_started", t0), make_event(shared, "run_failed", t0,
                                                              data={"error_type": "Boom"})])
    assert a.get(f"/runs/{shared}").json()["run"]["status"] == "success"
    assert b.get(f"/runs/{shared}").json()["run"]["status"] == "error"


def test_event_id_reuse_across_projects_is_not_a_duplicate(client):
    from tests.conftest import Tenant

    a, b = Tenant(client, "a"), Tenant(client, "b")
    e = make_event("r", "run_started")
    assert a.send([e]).json()["accepted"] == 1
    assert b.send([e]).json()["accepted"] == 1
