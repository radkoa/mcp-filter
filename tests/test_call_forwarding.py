from __future__ import annotations

import pytest

from mcp_filter.config import AllowRules, ConfigError, ServerConfig, UpstreamConfig
from mcp_filter.filter_server import build_server
from tests.fake_upstream import FakeUpstream


@pytest.mark.asyncio
async def test_call_forwarding_returns_upstream_content() -> None:
    upstream = FakeUpstream()
    config = ServerConfig(
        name="forward-test",
        include_health_tool=False,
        upstream=UpstreamConfig(transport="stdio", stdio_command="fake"),
        rules=AllowRules(allow_tools=["execute_sql"], rename_prefix="supabase_"),
    )

    app = await build_server(config, upstream=upstream)
    response = await app.call_tool("supabase_execute_sql", {"sql": "select 1"})

    assert response["content"][0]["text"] == "Query executed: select 1"
    assert upstream.calls == [("execute_sql", {"sql": "select 1"})]


@pytest.mark.asyncio
async def test_call_missing_required_argument_raises() -> None:
    upstream = FakeUpstream()
    config = ServerConfig(
        name="validation-test",
        include_health_tool=False,
        upstream=UpstreamConfig(transport="stdio", stdio_command="fake"),
        rules=AllowRules(allow_tools=["execute_sql"]),
    )

    app = await build_server(config, upstream=upstream)

    with pytest.raises(ConfigError, match="Missing required argument"):
        await app.call_tool("execute_sql", {})


@pytest.mark.asyncio
async def test_call_to_unexposed_tool_rejected() -> None:
    upstream = FakeUpstream()
    config = ServerConfig(
        name="blocked-test",
        include_health_tool=False,
        upstream=UpstreamConfig(transport="stdio", stdio_command="fake"),
        rules=AllowRules(allow_tools=["execute_sql"]),
    )

    app = await build_server(config, upstream=upstream)

    with pytest.raises(ConfigError, match="not exposed"):
        await app.call_tool("create_project", {"name": "demo", "region": "us-east-1"})


@pytest.mark.asyncio
async def test_health_handler_reports_status() -> None:
    upstream = FakeUpstream()
    config = ServerConfig(
        name="health-test",
        include_health_tool=True,
        upstream=UpstreamConfig(transport="stdio", stdio_command="fake"),
        rules=AllowRules(allow_tools=["execute_sql"]),
    )

    app = await build_server(config, upstream=upstream)
    response = await app.call_tool("health", {})

    # Health handler returns MCP content format: [{"type": "text", "text": "..."}]
    import json
    assert isinstance(response, list)
    assert len(response) == 1
    assert response[0]["type"] == "text"
    health_data = json.loads(response[0]["text"])

    assert health_data["upstream_ok"] is True
    assert health_data["tool_count"] == 1
    assert health_data["exposed_tools"] == ["execute_sql"]
    assert health_data["token_estimate"] >= 0


@pytest.mark.asyncio
async def test_health_handler_respects_prefix() -> None:
    upstream = FakeUpstream()
    config = ServerConfig(
        name="health-prefix",
        include_health_tool=True,
        upstream=UpstreamConfig(transport="stdio", stdio_command="fake"),
        rules=AllowRules(allow_tools=["execute_sql"], rename_prefix="supabase_"),
    )

    app = await build_server(config, upstream=upstream)
    response = await app.call_tool("supabase_health", {})

    # Health handler returns MCP content format: [{"type": "text", "text": "..."}]
    import json
    assert isinstance(response, list)
    health_data = json.loads(response[0]["text"])

    assert health_data["exposed_tools"] == ["supabase_execute_sql"]
