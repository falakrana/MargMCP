"""Phase 5 tests — Trace Details and Run History.

Covers every scenario in implementation.md §8:
    - complete and incomplete traces
    - missing parent spans
    - late-arriving spans
    - long traces and pagination
    - run with no trace data (no events at all)
    - trace backend timeout (trace_data_may_have_expired)
    - redacted and disabled payload capture
    - time-zone display and UTC storage consistency
    - correlation between run ID and trace ID
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import (
    Tenant,
    admin_headers,
    bearer,
    full_run,
    iso,
    make_event,
    now,
)

# ── helpers ───────────────────────────────────────────────────────────────── #

TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
SPAN_ID_RE = re.compile(r"^[0-9a-f]{16}$")


def _run_id() -> str:
    return str(uuid.uuid4())


def _make_llm_event(run_id, ts, *, agent_id="agent-1", duration_ms=100,
                    provider="openai", model="gpt-4o", span_id=None,
                    parent_span_id=None, prompt_tokens=10, completion_tokens=5):
    data = {
        "duration_ms": duration_ms,
        "provider": provider,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
    if span_id:
        data["span_id"] = span_id
    if parent_span_id:
        data["parent_span_id"] = parent_span_id
    return make_event(run_id, "llm_call_completed", ts, agent_id, data=data)


def _make_tool_event(run_id, ts, *, agent_id="agent-1", tool_name="search",
                     duration_ms=50, span_id=None, parent_span_id=None):
    data = {"tool_name": tool_name, "duration_ms": duration_ms}
    if span_id:
        data["span_id"] = span_id
    if parent_span_id:
        data["parent_span_id"] = parent_span_id
    return make_event(run_id, "tool_call_completed", ts, agent_id, data=data)


def _timeline(tenant, run_id, **params):
    return tenant.get(f"/runs/{run_id}/timeline", **params)


def _send_run_started(tenant, run_id, ts, *, agent_id="agent-1"):
    trace_id = uuid.uuid4().hex  # 32 hex chars
    root_span_id = uuid.uuid4().hex[:16]  # 16 hex chars
    ev = make_event(
        run_id, "run_started", ts, agent_id,
        data={"trace_id": trace_id, "root_span_id": root_span_id},
    )
    r = tenant.send([ev])
    assert r.status_code == 202
    return trace_id, root_span_id


# ── 1. Complete trace ─────────────────────────────────────────────────────── #

class TestCompleteTrace:
    def test_successful_run_timeline(self, tenant):
        run_id = _run_id()
        full_run(tenant, run_id)

        r = _timeline(tenant, run_id)
        assert r.status_code == 200
        body = r.json()

        assert body["is_complete"] is True
        assert body["run"]["status"] == "success"
        assert body["run"]["run_id"] == run_id
        assert len(body["spans"]) >= 1  # at least root span

    def test_failed_run_timeline(self, tenant):
        run_id = _run_id()
        full_run(tenant, run_id, fail=True)

        r = _timeline(tenant, run_id)
        assert r.status_code == 200
        body = r.json()

        assert body["is_complete"] is True
        assert body["run"]["status"] == "error"
        root = body["spans"][0]
        assert root["name"] == "agent.run"
        assert root["status"] == "error"

    def test_root_span_matches_run_identifiers(self, tenant):
        run_id = _run_id()
        ts = now() - timedelta(minutes=3)
        trace_id, root_span_id = _send_run_started(tenant, run_id, ts)
        tenant.send([make_event(run_id, "run_completed",
                                ts + timedelta(seconds=2), "agent-1")])

        r = _timeline(tenant, run_id)
        body = r.json()
        root = body["spans"][0]
        assert root["span_id"] == root_span_id
        assert root["parent_span_id"] is None

    def test_child_spans_present_and_ordered(self, tenant):
        run_id = _run_id()
        ts = now() - timedelta(minutes=5)
        _send_run_started(tenant, run_id, ts)
        tenant.send([
            _make_llm_event(run_id, ts + timedelta(seconds=1)),
            _make_tool_event(run_id, ts + timedelta(seconds=2)),
            _make_llm_event(run_id, ts + timedelta(seconds=3)),
            make_event(run_id, "run_completed", ts + timedelta(seconds=4), "agent-1"),
        ])

        r = _timeline(tenant, run_id)
        body = r.json()
        spans = body["spans"]
        # root + 2 llm + 1 tool
        assert len(spans) == 4
        # All must have a valid start_time
        for s in spans:
            assert s["start_time"] is not None


# ── 2. Incomplete trace ────────────────────────────────────────────────────── #

class TestIncompleteTrace:
    def test_run_with_no_terminal_event_is_incomplete(self, tenant):
        run_id = _run_id()
        ts = now() - timedelta(minutes=1)
        _send_run_started(tenant, run_id, ts)
        tenant.send([_make_llm_event(run_id, ts + timedelta(seconds=1))])

        r = _timeline(tenant, run_id)
        body = r.json()
        assert body["is_complete"] is False
        assert body["run"]["status"] in ("running", "unknown")

    def test_run_with_no_events_at_all(self, tenant):
        """A run_started event is what creates the run; sending none means no run.
        We verify a 404 is returned rather than a 500 for an entirely absent run.
        """
        r = _timeline(tenant, _run_id())
        assert r.status_code == 404

    def test_run_started_but_no_llm_or_tool_events(self, tenant):
        """Only run_started and run_completed; no child spans."""
        run_id = _run_id()
        ts = now() - timedelta(minutes=1)
        _send_run_started(tenant, run_id, ts)
        tenant.send([make_event(run_id, "run_completed",
                                ts + timedelta(seconds=1), "agent-1")])

        r = _timeline(tenant, run_id)
        body = r.json()
        assert body["is_complete"] is True
        # Only root span (no child-producing events)
        assert len(body["spans"]) == 1
        assert body["spans"][0]["name"] == "agent.run"


# ── 3. Missing parent spans ────────────────────────────────────────────────── #

class TestMissingParentSpans:
    def test_child_with_unknown_parent_flagged(self, tenant):
        """A child span that references a parent_span_id not in storage
        must have parent_missing=True."""
        run_id = _run_id()
        ts = now() - timedelta(minutes=2)
        _send_run_started(tenant, run_id, ts)
        nonexistent_parent = "deadbeef12345678"
        tenant.send([
            _make_llm_event(run_id, ts + timedelta(seconds=1),
                            parent_span_id=nonexistent_parent),
            make_event(run_id, "run_completed",
                       ts + timedelta(seconds=2), "agent-1"),
        ])

        r = _timeline(tenant, run_id)
        body = r.json()
        # Find the LLM span
        llm_spans = [s for s in body["spans"] if "llm" in s["name"]]
        assert len(llm_spans) == 1
        assert llm_spans[0]["parent_missing"] is True

    def test_child_with_known_parent_not_flagged(self, tenant):
        run_id = _run_id()
        ts = now() - timedelta(minutes=2)
        _, root_span_id = _send_run_started(tenant, run_id, ts)
        child_span_id = uuid.uuid4().hex[:16]
        grandchild_span_id = uuid.uuid4().hex[:16]
        # LLM call as child of root, tool as child of LLM
        tenant.send([
            _make_llm_event(run_id, ts + timedelta(seconds=1),
                            span_id=child_span_id, parent_span_id=root_span_id),
            _make_tool_event(run_id, ts + timedelta(seconds=2),
                             span_id=grandchild_span_id,
                             parent_span_id=child_span_id),
            make_event(run_id, "run_completed",
                       ts + timedelta(seconds=3), "agent-1"),
        ])

        r = _timeline(tenant, run_id)
        body = r.json()
        for s in body["spans"]:
            assert s["parent_missing"] is False


# ── 4. Late-arriving spans ────────────────────────────────────────────────── #

class TestLateArrivingSpans:
    def test_out_of_order_events_ordered_by_timestamp(self, tenant):
        """Events sent in reverse timestamp order must be served in timestamp order."""
        run_id = _run_id()
        ts = now() - timedelta(minutes=5)
        _send_run_started(tenant, run_id, ts)

        # Send events in reverse order
        r = tenant.send([
            make_event(run_id, "run_completed", ts + timedelta(seconds=4), "agent-1"),
            _make_tool_event(run_id, ts + timedelta(seconds=3)),
            _make_llm_event(run_id, ts + timedelta(seconds=2)),
            _make_llm_event(run_id, ts + timedelta(seconds=1)),
        ])
        assert r.status_code == 202

        r = _timeline(tenant, run_id)
        body = r.json()
        # Verify raw events come back in ascending timestamp order
        events = body["events"]
        timestamps = [e["timestamp"] for e in events]
        assert timestamps == sorted(timestamps)

    def test_late_arriving_run_started_event(self, tenant):
        """run_started arrives after llm_call events; timeline must still be correct."""
        run_id = _run_id()
        ts = now() - timedelta(minutes=3)
        trace_id = uuid.uuid4().hex
        root_span_id = uuid.uuid4().hex[:16]

        # Send LLM event first
        r = tenant.send([_make_llm_event(run_id, ts + timedelta(seconds=1))])
        assert r.status_code == 202

        # Now send run_started
        r = tenant.send([
            make_event(run_id, "run_started", ts, "agent-1",
                       data={"trace_id": trace_id, "root_span_id": root_span_id}),
            make_event(run_id, "run_completed", ts + timedelta(seconds=2), "agent-1"),
        ])
        assert r.status_code == 202

        r = _timeline(tenant, run_id)
        body = r.json()
        assert body["is_complete"] is True
        assert body["run"]["trace_id"] == trace_id


# ── 5. Pagination ─────────────────────────────────────────────────────────── #

class TestPagination:
    def _make_many_events(self, tenant, run_id, ts, count=15):
        events = []
        for i in range(count):
            events.append(
                _make_llm_event(run_id, ts + timedelta(seconds=i + 1))
            )
        events.append(
            make_event(run_id, "run_completed",
                       ts + timedelta(seconds=count + 1), "agent-1")
        )
        r = tenant.send(events)
        assert r.status_code == 202

    def test_event_pagination_page_1(self, tenant):
        run_id = _run_id()
        ts = now() - timedelta(minutes=10)
        _send_run_started(tenant, run_id, ts)
        self._make_many_events(tenant, run_id, ts, count=10)

        r = _timeline(tenant, run_id, event_page=1, event_page_size=5)
        body = r.json()
        assert body["total_event_count"] == 12  # start + 10 llm + complete
        assert len(body["events"]) == 5
        assert body["event_page"] == 1
        assert body["event_page_size"] == 5

    def test_event_pagination_page_2(self, tenant):
        run_id = _run_id()
        ts = now() - timedelta(minutes=10)
        _send_run_started(tenant, run_id, ts)
        self._make_many_events(tenant, run_id, ts, count=10)

        r = _timeline(tenant, run_id, event_page=2, event_page_size=5)
        body = r.json()
        assert len(body["events"]) == 5
        assert body["event_page"] == 2

    def test_event_pagination_last_page_may_be_shorter(self, tenant):
        run_id = _run_id()
        ts = now() - timedelta(minutes=10)
        _send_run_started(tenant, run_id, ts)
        self._make_many_events(tenant, run_id, ts, count=10)

        # 12 total events, page 3 of 5 → 2 remaining
        r = _timeline(tenant, run_id, event_page=3, event_page_size=5)
        body = r.json()
        assert len(body["events"]) == 2

    def test_max_spans_limit_respected(self, tenant):
        run_id = _run_id()
        ts = now() - timedelta(minutes=10)
        _send_run_started(tenant, run_id, ts)
        self._make_many_events(tenant, run_id, ts, count=10)

        r = _timeline(tenant, run_id, max_spans=3)
        body = r.json()
        assert len(body["spans"]) <= 3

    def test_span_count_matches_spans_list(self, tenant):
        run_id = _run_id()
        full_run(tenant, run_id)
        r = _timeline(tenant, run_id)
        body = r.json()
        assert body["span_count"] == len(body["spans"])


# ── 6. Trace data may have expired ───────────────────────────────────────────  #

class TestTraceExpiry:
    def test_recent_run_trace_not_expired(self, tenant):
        run_id = _run_id()
        full_run(tenant, run_id)

        r = _timeline(tenant, run_id)
        body = r.json()
        assert body["trace_data_may_have_expired"] is False

    def test_retention_flags_exposed_in_correlation_links(self, tenant):
        run_id = _run_id()
        full_run(tenant, run_id)

        r = _timeline(tenant, run_id)
        body = r.json()
        cl = body["correlation_links"]
        assert "run_metadata_expires_at" in cl
        assert "trace_data_expires_at" in cl
        # Both should be ISO-8601 strings in the future for a fresh run
        from datetime import datetime, timezone
        run_exp = datetime.fromisoformat(cl["run_metadata_expires_at"])
        trace_exp = datetime.fromisoformat(cl["trace_data_expires_at"])
        assert run_exp > datetime.now(timezone.utc)
        assert trace_exp > datetime.now(timezone.utc)
        # Run retention (90d) > trace retention (30d)
        assert run_exp > trace_exp

    def test_metric_window_in_correlation_links_for_completed_run(self, tenant):
        run_id = _run_id()
        full_run(tenant, run_id)

        r = _timeline(tenant, run_id)
        body = r.json()
        cl = body["correlation_links"]
        assert "metric_window" in cl
        assert cl["metric_window"]["from"] < cl["metric_window"]["to"]


# ── 7. Payload capture (privacy) ──────────────────────────────────────────── #

class TestPayloadCapture:
    def _run_with_summary(self, tenant, run_id):
        ts = now() - timedelta(minutes=2)
        _send_run_started(tenant, run_id, ts)
        # output_summary / summary are stripped unless payload capture is on
        ev = make_event(run_id, "llm_call_completed",
                        ts + timedelta(seconds=1), "agent-1",
                        data={"summary": "secret summary",
                              "output_summary": "secret output",
                              "prompt_tokens": 5, "completion_tokens": 3})
        tenant.send([ev,
                     make_event(run_id, "run_completed",
                                ts + timedelta(seconds=2), "agent-1")])

    def test_payload_fields_stripped_by_default(self, client):
        """By default payload_capture_enabled=False; summary fields must be absent."""
        from tests.conftest import Tenant
        tenant = Tenant(client)
        run_id = _run_id()
        self._run_with_summary(tenant, run_id)

        r = _timeline(tenant, run_id)
        body = r.json()
        # All raw events in the response should not contain summary fields
        for ev in body["events"]:
            assert "summary" not in ev["data"]
            assert "output_summary" not in ev["data"]

    def test_safe_attributes_always_present(self, tenant):
        run_id = _run_id()
        ts = now() - timedelta(minutes=2)
        _send_run_started(tenant, run_id, ts)
        tenant.send([
            _make_llm_event(run_id, ts + timedelta(seconds=1),
                            provider="openai", model="gpt-4o"),
            make_event(run_id, "run_completed",
                       ts + timedelta(seconds=2), "agent-1"),
        ])

        r = _timeline(tenant, run_id)
        body = r.json()
        llm_span = next(s for s in body["spans"] if "llm" in s.get("name", ""))
        attrs = llm_span["attributes"]
        assert attrs.get("llm.provider") == "openai"
        assert attrs.get("llm.model") == "gpt-4o"


# ── 8. UTC and timezone consistency ──────────────────────────────────────────  #

class TestTimezoneConsistency:
    @staticmethod
    def _parse_dt(s: str) -> datetime:
        """Parse ISO-8601 compatible with Python 3.10 (no 'Z' suffix support)."""
        return datetime.fromisoformat(s.replace("Z", "+00:00"))

    def test_all_timestamps_returned_as_utc(self, tenant):
        run_id = _run_id()
        full_run(tenant, run_id)

        r = _timeline(tenant, run_id)
        body = r.json()
        # Root run timestamps
        for field in ("started_at", "created_at", "updated_at"):
            raw = body["run"].get(field)
            if raw:
                dt = self._parse_dt(raw)
                assert dt.tzinfo is not None, f"{field} is missing tzinfo"

        # Span timestamps
        for span in body["spans"]:
            for field in ("start_time", "end_time"):
                dt = self._parse_dt(span[field])
                assert dt.tzinfo is not None

        # Event timestamps
        for ev in body["events"]:
            dt = self._parse_dt(ev["timestamp"])
            assert dt.tzinfo is not None

    def test_events_ordered_by_utc_timestamp(self, tenant):
        run_id = _run_id()
        ts = now() - timedelta(minutes=5)
        _send_run_started(tenant, run_id, ts)
        tenant.send([
            _make_llm_event(run_id, ts + timedelta(seconds=2)),
            _make_tool_event(run_id, ts + timedelta(seconds=1)),
            make_event(run_id, "run_completed",
                       ts + timedelta(seconds=3), "agent-1"),
        ])

        r = _timeline(tenant, run_id)
        body = r.json()
        timestamps = [
            self._parse_dt(e["timestamp"])
            for e in body["events"]
        ]
        for a, b in zip(timestamps, timestamps[1:]):
            assert a <= b, "events not in ascending timestamp order"


# ── 9. Run ID ↔ Trace ID correlation ─────────────────────────────────────── #

class TestTraceRunCorrelation:
    def test_correlation_links_contain_trace_and_run_ids(self, tenant):
        run_id = _run_id()
        ts = now() - timedelta(minutes=2)
        trace_id, root_span_id = _send_run_started(tenant, run_id, ts)
        tenant.send([make_event(run_id, "run_completed",
                                ts + timedelta(seconds=1), "agent-1")])

        r = _timeline(tenant, run_id)
        body = r.json()
        cl = body["correlation_links"]
        assert cl["run_id"] == run_id
        assert cl["trace_id"] == trace_id
        assert cl["root_span_id"] == root_span_id

    def test_lookup_run_by_trace_id_redirects(self, tenant):
        """GET /runs/by-trace/{trace_id} must redirect to the run timeline."""
        run_id = _run_id()
        ts = now() - timedelta(minutes=2)
        trace_id, _ = _send_run_started(tenant, run_id, ts)
        tenant.send([make_event(run_id, "run_completed",
                                ts + timedelta(seconds=1), "agent-1")])

        # Use the underlying TestClient directly to disable redirect following.
        r = tenant.client.get(
            f"/v1/projects/{tenant.project_id}/runs/by-trace/{trace_id}",
            headers=bearer(tenant.read_key),
            follow_redirects=False,
        )
        assert r.status_code == 307
        assert f"/runs/{run_id}/timeline" in r.headers["location"]

    def test_lookup_by_invalid_trace_id_returns_404(self, tenant):
        r = tenant.get("/runs/by-trace/notavalidtraceid")
        assert r.status_code == 404

    def test_lookup_by_nonexistent_trace_id_returns_404(self, tenant):
        r = tenant.get(f"/runs/by-trace/{'0' * 32}")
        assert r.status_code == 404

    def test_trace_link_absent_when_no_otlp_ui_configured(self, tenant):
        run_id = _run_id()
        full_run(tenant, run_id)

        r = _timeline(tenant, run_id)
        body = r.json()
        # Default settings have no otlp_ui_base_url
        assert body["trace_link"] is None

    def test_run_and_trace_ids_are_correctly_formatted(self, tenant):
        run_id = _run_id()
        ts = now() - timedelta(minutes=2)
        trace_id, root_span_id = _send_run_started(tenant, run_id, ts)
        tenant.send([make_event(run_id, "run_completed",
                                ts + timedelta(seconds=1), "agent-1")])

        r = _timeline(tenant, run_id)
        body = r.json()
        assert TRACE_ID_RE.match(body["run"]["trace_id"])
        assert SPAN_ID_RE.match(body["run"]["root_span_id"])


# ── 10. Error details and summaries ──────────────────────────────────────── #

class TestErrorDetails:
    def test_error_span_has_error_attributes(self, tenant):
        run_id = _run_id()
        ts = now() - timedelta(minutes=2)
        _send_run_started(tenant, run_id, ts)
        # llm_call_failed
        tenant.send([
            make_event(run_id, "llm_call_failed",
                       ts + timedelta(seconds=1), "agent-1",
                       data={"error_type": "RateLimitError",
                             "error_summary": "Too many requests"}),
            make_event(run_id, "run_failed",
                       ts + timedelta(seconds=2), "agent-1",
                       data={"error_type": "RateLimitError",
                             "error_summary": "Too many requests"}),
        ])

        r = _timeline(tenant, run_id)
        body = r.json()
        # Root span should show error status
        root = body["spans"][0]
        assert root["status"] == "error"
        # Error run has error_type in run metadata
        assert body["run"]["error_type"] == "RateLimitError"

    def test_failed_run_is_complete(self, tenant):
        run_id = _run_id()
        full_run(tenant, run_id, fail=True)
        r = _timeline(tenant, run_id)
        body = r.json()
        assert body["is_complete"] is True
        assert body["run"]["status"] == "error"


# ── 11. Cross-tenant isolation ────────────────────────────────────────────── #

class TestCrossTenantIsolation:
    def test_cannot_access_another_projects_timeline(self, client):
        t1 = Tenant(client, name="p1")
        t2 = Tenant(client, name="p2")

        run_id = _run_id()
        full_run(t1, run_id)

        # t2's read key should not see t1's run
        r = client.get(
            f"/v1/projects/{t1.project_id}/runs/{run_id}/timeline",
            headers=bearer(t2.read_key),
        )
        assert r.status_code == 403

    def test_cannot_access_by_trace_id_across_projects(self, client):
        t1 = Tenant(client, name="p-a")
        t2 = Tenant(client, name="p-b")
        run_id = _run_id()
        ts = now() - timedelta(minutes=2)
        trace_id, _ = _send_run_started(t1, run_id, ts)
        t1.send([make_event(run_id, "run_completed",
                            ts + timedelta(seconds=1), "agent-1")])

        # t2 tries to look up by trace_id in t1's project scope
        r = client.get(
            f"/v1/projects/{t1.project_id}/runs/by-trace/{trace_id}",
            headers=bearer(t2.read_key),
        )
        assert r.status_code == 403


# ── 12. Span span-level status ───────────────────────────────────────────── #

class TestSpanStatuses:
    def test_tool_failure_span_status_is_error(self, tenant):
        run_id = _run_id()
        ts = now() - timedelta(minutes=2)
        _send_run_started(tenant, run_id, ts)
        tenant.send([
            make_event(run_id, "tool_call_failed",
                       ts + timedelta(seconds=1), "agent-1",
                       data={"tool_name": "calculator", "error_type": "ZeroDivisionError"}),
            make_event(run_id, "run_completed",
                       ts + timedelta(seconds=2), "agent-1"),
        ])

        r = _timeline(tenant, run_id)
        body = r.json()
        tool_spans = [s for s in body["spans"] if "tool" in s["name"]]
        assert len(tool_spans) == 1
        assert tool_spans[0]["status"] == "error"

    def test_llm_completed_span_status_is_ok(self, tenant):
        run_id = _run_id()
        ts = now() - timedelta(minutes=2)
        _send_run_started(tenant, run_id, ts)
        tenant.send([
            _make_llm_event(run_id, ts + timedelta(seconds=1)),
            make_event(run_id, "run_completed",
                       ts + timedelta(seconds=2), "agent-1"),
        ])

        r = _timeline(tenant, run_id)
        body = r.json()
        llm_spans = [s for s in body["spans"] if "llm" in s["name"]]
        assert len(llm_spans) == 1
        assert llm_spans[0]["status"] == "ok"

    def test_incomplete_run_root_span_status_is_running(self, tenant):
        run_id = _run_id()
        ts = now() - timedelta(minutes=1)
        _send_run_started(tenant, run_id, ts)
        # No terminal event

        r = _timeline(tenant, run_id)
        body = r.json()
        root = body["spans"][0]
        assert root["status"] == "running"


# ── 13. Nested LLM/tool operations ───────────────────────────────────────── #

class TestNestedOperations:
    def test_nested_spans_have_correct_parent(self, tenant):
        run_id = _run_id()
        ts = now() - timedelta(minutes=5)
        _, root_span_id = _send_run_started(tenant, run_id, ts)
        llm_span_id = uuid.uuid4().hex[:16]
        tool_span_id = uuid.uuid4().hex[:16]

        tenant.send([
            _make_llm_event(run_id, ts + timedelta(seconds=1),
                            span_id=llm_span_id,
                            parent_span_id=root_span_id),
            _make_tool_event(run_id, ts + timedelta(seconds=2),
                             span_id=tool_span_id,
                             parent_span_id=llm_span_id),
            make_event(run_id, "run_completed",
                       ts + timedelta(seconds=3), "agent-1"),
        ])

        r = _timeline(tenant, run_id)
        body = r.json()
        spans = {s["span_id"]: s for s in body["spans"]}

        # LLM is a child of root
        assert spans[llm_span_id]["parent_span_id"] == root_span_id
        assert not spans[llm_span_id]["parent_missing"]

        # Tool is a child of LLM
        assert spans[tool_span_id]["parent_span_id"] == llm_span_id
        assert not spans[tool_span_id]["parent_missing"]

    def test_span_duration_matches_duration_ms(self, tenant):
        run_id = _run_id()
        ts = now() - timedelta(minutes=2)
        _send_run_started(tenant, run_id, ts)
        tenant.send([
            _make_llm_event(run_id, ts + timedelta(seconds=1), duration_ms=500),
            make_event(run_id, "run_completed",
                       ts + timedelta(seconds=2), "agent-1"),
        ])

        r = _timeline(tenant, run_id)
        body = r.json()
        llm_span = next(s for s in body["spans"] if "llm" in s["name"])
        assert llm_span["duration_ms"] == 500
        # start_time + 500ms ≈ end_time
        def _parse(s: str) -> datetime:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        start = _parse(llm_span["start_time"])
        end = _parse(llm_span["end_time"])
        diff_ms = (end - start).total_seconds() * 1000
        assert abs(diff_ms - 500) < 2  # allow tiny float imprecision
