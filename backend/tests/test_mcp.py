"""Phase 7: MCP monitoring tools — validation, authorisation, bounds, safety,
and an end-to-end MCP protocol smoke test over stdio."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import timedelta

import pytest
from sqlalchemy.exc import OperationalError

from agentops_backend.mcp_server import DIAGNOSTIC_TOOL_NAMES, TOOL_NAMES, build_server
from agentops_backend.mcp_tools import MonitoringTools, ToolError

from .conftest import SECRET, Tenant, full_run, make_event, now

SECRET_TEXT = "SECRET-PAYLOAD-DO-NOT-LEAK"


@pytest.fixture
def tools(client):
    st = client.app.state
    return MonitoringTools(st.settings, st.session_factory)


@pytest.fixture
def seeded(client, tools):
    """Tenant with two agents, successful + failed runs, and a payload event."""
    t = Tenant(client, "mcp-main")
    full_run(t, "run-ok", agent_id="agent-1", duration=2)
    full_run(t, "run-bad", agent_id="agent-1", fail=True, duration=5)
    full_run(t, "run-other", agent_id="agent-2", duration=1)
    r = t.send([make_event("run-ok", "output_summary", data={"summary": SECRET_TEXT})])
    assert r.status_code == 202, r.text
    return t


def code_of(excinfo) -> str:
    return excinfo.value.code


# ------------------------------- happy paths -------------------------------- #
class TestToolOutputs:
    def test_list_agents(self, tools, seeded):
        out = tools.list_agents(seeded.read_key)
        assert out["kind"] == "summary"
        assert {a["agent_id"] for a in out["items"]} == {"agent-1", "agent-2"}
        assert out["total"] == 2 and out["truncated"] is False
        assert out["source"]["project_id"] == seeded.project_id
        assert out["source"]["generated_at"].endswith("Z")

    def test_get_agent_metrics(self, tools, seeded):
        out = tools.get_agent_metrics(seeded.read_key, "agent-1")
        m = out["metrics"]
        assert m["total_runs"] == 2
        assert m["runs_by_status"] == {"success": 1, "error": 1}
        assert m["error_rate"] == 0.5
        assert m["duration_ms"]["max"] == 5000
        assert m["llm_call_count"] == 2 and m["total_tokens"] == 30
        assert out["unavailable"] == []

    def test_metrics_unavailable_indicator_when_no_runs(self, tools, seeded):
        out = tools.get_agent_metrics(
            seeded.read_key, "agent-1",
            started_after=(now() - timedelta(days=3)).isoformat(),
            started_before=(now() - timedelta(days=2)).isoformat(),
        )
        assert out["metrics"]["total_runs"] == 0
        assert out["metrics"]["error_rate"] is None
        assert len(out["unavailable"]) == 2

    def test_list_runs_filters_and_pagination(self, tools, seeded):
        out = tools.list_runs(seeded.read_key, agent_id="agent-1", status="error")
        assert [r["run_id"] for r in out["items"]] == ["run-bad"]
        page1 = tools.list_runs(seeded.read_key, page=1, page_size=2)
        assert len(page1["items"]) == 2 and page1["total"] == 3 and page1["truncated"] is True
        page2 = tools.list_runs(seeded.read_key, page=2, page_size=2)
        assert len(page2["items"]) == 1 and page2["truncated"] is False

    def test_get_run_details(self, tools, seeded):
        out = tools.get_run_details(seeded.read_key, "run-bad")
        assert out["run"]["status"] == "error"
        assert out["run"]["error_type"] == "TimeoutError"
        assert out["event_type_counts"]["run_failed"] == 1
        assert "events" not in out

    def test_get_trace(self, tools, seeded):
        out = tools.get_trace(seeded.read_key, "run-ok")
        assert out["kind"] == "detail"
        assert out["is_complete"] is True
        assert out["spans"][0]["name"] == "agent.run"
        assert out["span_count"] == len(out["spans"]) >= 3
        assert out["spans"][0]["parent_span_id"] is None

    def test_get_trace_incomplete_flagged(self, tools, client):
        t = Tenant(client, "mcp-incomplete")
        r = t.send([make_event("run-open", "run_started")])
        assert r.status_code == 202, r.text
        assert tools.get_trace(t.read_key, "run-open")["is_complete"] is False

    def test_get_error_summary(self, tools, seeded):
        out = tools.get_error_summary(seeded.read_key)
        assert out["total_runs"] == 3 and out["error_runs"] == 1
        assert out["groups"][0]["error_type"] == "TimeoutError"
        assert out["groups"][0]["agent_id"] == "agent-1"

    def test_compare_runs(self, tools, seeded):
        out = tools.compare_runs(seeded.read_key, "run-ok", "run-bad")
        c = out["comparison"]
        assert c["same_agent"] is True and c["status_changed"] is True
        assert c["deltas_b_minus_a"]["duration_ms"] == 3000
        assert out["run_a"]["run_id"] == "run-ok"

    def test_explicit_matching_project_id_allowed(self, tools, seeded):
        out = tools.list_agents(seeded.read_key, project_id=seeded.project_id)
        assert out["total"] == 2


# ------------------------------ authn / authz ------------------------------- #
class TestAuth:
    @pytest.mark.parametrize("token", [None, "", "aop_deadbeef_notarealkey", "garbage"])
    def test_missing_or_invalid_key(self, tools, seeded, token):
        with pytest.raises(ToolError) as e:
            tools.list_agents(token)
        assert code_of(e) == "unauthorized"

    def test_ingest_only_key_rejected(self, tools, seeded):
        with pytest.raises(ToolError) as e:
            tools.list_agents(seeded.ingest_key)
        assert code_of(e) == "insufficient_scope"

    def test_cross_project_id_denied(self, tools, client, seeded):
        other = Tenant(client, "mcp-other")
        with pytest.raises(ToolError) as e:
            tools.list_runs(other.read_key, project_id=seeded.project_id)
        assert code_of(e) == "project_access_denied"

    def test_cross_tenant_data_not_visible(self, tools, client, seeded):
        other = Tenant(client, "mcp-other")
        assert tools.list_agents(other.read_key)["items"] == []
        for fn, args in (
            (tools.get_run_details, ("run-ok",)),
            (tools.get_trace, ("run-ok",)),
            (tools.compare_runs, ("run-ok", "run-bad")),
        ):
            with pytest.raises(ToolError) as e:
                fn(other.read_key, *args)
            assert code_of(e) == "not_found"
        with pytest.raises(ToolError) as e:
            tools.get_agent_metrics(other.read_key, "agent-1")
        assert code_of(e) == "not_found"
        assert tools.get_error_summary(other.read_key)["total_runs"] == 0

    def test_revoked_key_stops_working(self, tools, client, seeded):
        from agentops_backend.models import ApiKey
        from agentops_backend.auth import _parse_prefix
        from sqlalchemy import select
        from datetime import datetime, timezone

        assert tools.list_agents(seeded.read_key)
        with client.app.state.session_factory() as s:
            row = s.execute(
                select(ApiKey).where(ApiKey.key_prefix == _parse_prefix(seeded.read_key))
            ).scalar_one()
            row.revoked_at = datetime.now(timezone.utc)
            s.commit()
        with pytest.raises(ToolError) as e:
            tools.list_agents(seeded.read_key)
        assert code_of(e) == "unauthorized"


# --------------------------- validation and limits -------------------------- #
class TestValidationAndBounds:
    @pytest.mark.parametrize("bad", ["../etc/passwd", "a b", "x" * 65, "run;drop", "-leading"])
    def test_malformed_ids(self, tools, seeded, bad):
        for call in (
            lambda: tools.get_run_details(seeded.read_key, bad),
            lambda: tools.get_trace(seeded.read_key, bad),
            lambda: tools.get_agent_metrics(seeded.read_key, bad),
            lambda: tools.list_runs(seeded.read_key, agent_id=bad),
            lambda: tools.compare_runs(seeded.read_key, "run-ok", bad),
            lambda: tools.list_agents(seeded.read_key, project_id=bad),
        ):
            with pytest.raises(ToolError) as e:
                call()
            assert code_of(e) == "invalid_argument"

    def test_required_ids(self, tools, seeded):
        with pytest.raises(ToolError) as e:
            tools.get_run_details(seeded.read_key, "")
        assert code_of(e) == "invalid_argument"

    def test_malformed_time(self, tools, seeded):
        with pytest.raises(ToolError) as e:
            tools.list_runs(seeded.read_key, started_after="yesterday")
        assert code_of(e) == "invalid_time_range"

    def test_reversed_time_range(self, tools, seeded):
        n = now()
        with pytest.raises(ToolError) as e:
            tools.list_runs(
                seeded.read_key, started_after=n.isoformat(),
                started_before=(n - timedelta(hours=1)).isoformat(),
            )
        assert code_of(e) == "invalid_time_range"

    def test_unbounded_window_rejected(self, tools, seeded):
        n = now()
        with pytest.raises(ToolError) as e:
            tools.get_error_summary(
                seeded.read_key, started_after=(n - timedelta(days=365)).isoformat(),
                started_before=n.isoformat(),
            )
        assert code_of(e) == "time_range_too_large"
        with pytest.raises(ToolError) as e:  # open-ended 'after' alone is also bounded
            tools.get_agent_metrics(
                seeded.read_key, "agent-1",
                started_after=(n - timedelta(days=365)).isoformat(),
            )
        assert code_of(e) == "time_range_too_large"

    def test_z_suffix_timestamps_accepted(self, tools, seeded):
        n = now()
        out = tools.list_runs(
            seeded.read_key,
            started_after=(n - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        assert out["total"] == 3

    @pytest.mark.parametrize("size", [0, -1, 51, 10_000])
    def test_page_size_capped(self, tools, seeded, size):
        with pytest.raises(ToolError) as e:
            tools.list_runs(seeded.read_key, page_size=size)
        assert code_of(e) == "invalid_argument"

    def test_bad_page_status_env_limit_spans(self, tools, seeded):
        for call in (
            lambda: tools.list_runs(seeded.read_key, page=0),
            lambda: tools.list_runs(seeded.read_key, status="exploded"),
            lambda: tools.list_runs(seeded.read_key, environment="prod"),
            lambda: tools.get_error_summary(seeded.read_key, limit=10_000),
            lambda: tools.get_trace(seeded.read_key, "run-ok", max_spans=100_000),
        ):
            with pytest.raises(ToolError) as e:
                call()
            assert code_of(e) == "invalid_argument"

    def test_unknown_run_is_controlled_not_found(self, tools, seeded):
        with pytest.raises(ToolError) as e:
            tools.get_run_details(seeded.read_key, "nope")
        assert code_of(e) == "not_found"


# ------------------------------ failure handling ---------------------------- #
class TestFailureModes:
    def test_database_unavailable(self, client):
        def broken():
            raise OperationalError("SELECT secret FROM t", {}, Exception("password=hunter2"))

        tools = MonitoringTools(client.app.state.settings, broken)
        with pytest.raises(ToolError) as e:
            tools.list_agents("aop_deadbeef_x")
        assert code_of(e) == "storage_unavailable"
        assert "hunter2" not in str(e.value) and "SELECT" not in str(e.value)

    def test_unexpected_exception_is_sanitised(self, client):
        def broken():
            raise RuntimeError("/internal/path password=hunter2")

        tools = MonitoringTools(client.app.state.settings, broken)
        with pytest.raises(ToolError) as e:
            tools.list_agents("aop_deadbeef_x")
        assert code_of(e) == "internal_error"
        assert "hunter2" not in str(e.value) and "/internal" not in str(e.value)


# ------------------------------- output safety ------------------------------ #
class TestOutputSafety:
    def test_no_secrets_or_payloads_in_any_tool_output(self, tools, seeded):
        outputs = [
            tools.list_agents(seeded.read_key),
            tools.get_agent_metrics(seeded.read_key, "agent-1"),
            tools.list_runs(seeded.read_key),
            tools.get_run_details(seeded.read_key, "run-ok"),
            tools.get_trace(seeded.read_key, "run-ok"),
            tools.get_error_summary(seeded.read_key),
            tools.compare_runs(seeded.read_key, "run-ok", "run-bad"),
        ]
        blob = json.dumps(outputs)
        for forbidden in (
            SECRET_TEXT, seeded.read_key, seeded.ingest_key, SECRET, "key_hash", "Traceback",
        ):
            assert forbidden not in blob

    def test_run_metadata_hidden_unless_payload_capture_enabled(self, tools, seeded):
        out = tools.get_run_details(seeded.read_key, "run-ok")
        assert "metadata" not in out["run"]

    def test_error_text_truncated(self, tools):
        class R:
            run_id = "r"; agent_id = "a"; environment = "production"; status = "error"
            started_at = now(); ended_at = None; duration_ms = None
            error_type = "E"; error_summary = "x" * 5000; deployment_version = None
            llm_call_count = tool_call_count = 0
            total_prompt_tokens = total_completion_tokens = total_tokens = 0
            trace_id = "t"; metadata = {"k": "v"}

        assert len(tools._run_summary(R)["error_summary"]) == 256


# ------------------------------- read-only surface -------------------------- #
class TestReadOnlySurface:
    def test_exact_tool_set_and_annotations(self, client):
        st = client.app.state
        server = build_server(st.settings, st.session_factory)
        listed = asyncio.run(server.list_tools())
        assert {t.name for t in listed} == set(TOOL_NAMES) | set(DIAGNOSTIC_TOOL_NAMES)
        for t in listed:
            assert t.annotations is not None
            assert t.annotations.readOnlyHint is True
            assert t.annotations.destructiveHint is False
            assert "ctx" not in json.dumps(t.inputSchema)  # context is not exposed

    def test_tool_calls_do_not_modify_data(self, client, tools, seeded):
        from sqlalchemy import func, select
        from agentops_backend.models import Event, Run

        def counts():
            with client.app.state.session_factory() as s:
                return (
                    s.execute(select(func.count()).select_from(Run)).scalar_one(),
                    s.execute(select(func.count()).select_from(Event)).scalar_one(),
                )

        before = counts()
        tools.list_agents(seeded.read_key)
        tools.get_trace(seeded.read_key, "run-ok")
        tools.compare_runs(seeded.read_key, "run-ok", "run-bad")
        assert counts() == before


# ------------------------------ protocol smoke test ------------------------- #
class TestMcpProtocolSmoke:
    def test_stdio_client_lists_and_calls_tools(self, client, db_path, tmp_path, seeded):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        env = {
            **os.environ,
            "AGENTOPS_DATABASE_URL": f"sqlite:///{db_path}",
            "AGENTOPS_SECRET_KEY": SECRET,
            "AGENTOPS_ENV": "development",
            "AGENTOPS_MCP_API_KEY": seeded.read_key,
        }
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "agentops_backend.mcp_server"],
            env=env, cwd=str(tmp_path),  # keeps a developer's real .env out of the test
        )

        async def scenario():
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    names = {t.name for t in listed.tools}

                    agents = await session.call_tool("list_agents", {})
                    runs = await session.call_tool("list_runs", {"status": "error"})
                    trace = await session.call_tool("get_trace", {"run_id": "run-ok"})
                    bad = await session.call_tool("get_run_details", {"run_id": "../x"})
                    denied = await session.call_tool(
                        "list_agents", {"project_id": "someone-elses-project"}
                    )
                    return names, agents, runs, trace, bad, denied

        names, agents, runs, trace, bad, denied = asyncio.run(
            asyncio.wait_for(scenario(), timeout=60)
        )
        assert names == set(TOOL_NAMES) | set(DIAGNOSTIC_TOOL_NAMES)
        assert agents.isError is False
        assert {a["agent_id"] for a in agents.structuredContent["items"]} == {"agent-1", "agent-2"}
        assert [r["run_id"] for r in runs.structuredContent["items"]] == ["run-bad"]
        assert trace.structuredContent["spans"][0]["name"] == "agent.run"
        assert bad.isError is True and "invalid_argument" in bad.content[0].text
        assert denied.isError is True and "project_access_denied" in denied.content[0].text
        assert seeded.read_key not in json.dumps(
            [agents.structuredContent, runs.structuredContent, trace.structuredContent]
        )

    def test_stdio_without_key_is_rejected(self, db_path, tmp_path, client):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        env = {k: v for k, v in os.environ.items() if k != "AGENTOPS_MCP_API_KEY"}
        env.update(
            AGENTOPS_DATABASE_URL=f"sqlite:///{db_path}",
            AGENTOPS_SECRET_KEY=SECRET, AGENTOPS_ENV="development",
        )
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "agentops_backend.mcp_server"],
            env=env, cwd=str(tmp_path),
        )

        async def scenario():
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await session.call_tool("list_agents", {})

        res = asyncio.run(asyncio.wait_for(scenario(), timeout=60))
        assert res.isError is True and "unauthorized" in res.content[0].text
