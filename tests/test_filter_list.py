from __future__ import annotations

import pytest

from mcp_filter.config import AllowRules, ConfigError, ServerConfig, UpstreamConfig
from mcp_filter.filter_server import build_server, filter_tools
from mcp_filter.upstream import ToolSchema
from tests.fake_upstream import FakeUpstream


@pytest.mark.asyncio
async def test_filter_exact_tool_name() -> None:
    upstream = FakeUpstream()
    tools = await upstream.list_tools()

    rules = AllowRules(allow_tools=["execute_sql"])
    filtered = filter_tools(tools, rules)

    assert len(filtered) == 1
    assert filtered[0].public_name == "execute_sql"
    assert filtered[0].upstream_name == "execute_sql"


@pytest.mark.asyncio
async def test_filter_multiple_exact_names() -> None:
    upstream = FakeUpstream()
    tools = await upstream.list_tools()

    rules = AllowRules(allow_tools=["execute_sql", "create_project"])
    filtered = filter_tools(tools, rules)

    assert {tool.public_name for tool in filtered} == {"execute_sql", "create_project"}


@pytest.mark.asyncio
async def test_filter_with_patterns() -> None:
    upstream = FakeUpstream()
    tools = await upstream.list_tools()

    rules = AllowRules(allow_patterns=[r"^execute_.*"])
    filtered = filter_tools(tools, rules)

    assert len(filtered) == 1
    assert filtered[0].public_name == "execute_sql"


@pytest.mark.asyncio
async def test_filter_with_deny_patterns() -> None:
    upstream = FakeUpstream()
    tools = await upstream.list_tools()

    rules = AllowRules(
        allow_patterns=[".*"],
        deny_patterns=[r"delete_.*"],
    )
    filtered = filter_tools(tools, rules)

    names = {tool.public_name for tool in filtered}
    assert "delete_branch" not in names
    assert names == {"execute_sql", "create_project"}


@pytest.mark.asyncio
async def test_filter_with_rename_prefix() -> None:
    upstream = FakeUpstream()
    tools = await upstream.list_tools()

    rules = AllowRules(allow_tools=["execute_sql"], rename_prefix="supabase_")
    filtered = filter_tools(tools, rules)

    assert len(filtered) == 1
    assert filtered[0].public_name == "supabase_execute_sql"
    assert filtered[0].upstream_name == "execute_sql"


def test_filter_rename_collision_raises() -> None:
    tools = [
        ToolSchema(name="dup", description="Duplicate", input_schema={"type": "object"}),
        ToolSchema(name="dup", description="Duplicate again", input_schema={"type": "object"}),
    ]
    rules = AllowRules(allow_patterns=["dup"])

    with pytest.raises(ConfigError, match="collision"):
        filter_tools(tools, rules)


@pytest.mark.asyncio
async def test_filter_no_matches_raises() -> None:
    upstream = FakeUpstream()
    tools = await upstream.list_tools()

    rules = AllowRules(allow_tools=["does_not_exist"])

    with pytest.raises(ConfigError, match="No tools remain"):
        filter_tools(tools, rules)


@pytest.mark.asyncio
async def test_filter_precedence_prefers_allow_tools() -> None:
    upstream = FakeUpstream()
    tools = await upstream.list_tools()

    rules = AllowRules(allow_tools=["execute_sql"], allow_patterns=[".*"])
    filtered = filter_tools(tools, rules)

    assert len(filtered) == 1
    assert filtered[0].public_name == "execute_sql"


@pytest.mark.asyncio
async def test_build_server_includes_health() -> None:
    upstream = FakeUpstream()
    config = ServerConfig(
        name="test",
        include_health_tool=True,
        show_token_estimates=True,
        upstream=UpstreamConfig(transport="stdio", stdio_command="fake"),
        rules=AllowRules(allow_tools=["execute_sql"], rename_prefix="supabase_"),
    )

    app = await build_server(config, upstream=upstream)
    public_names = [tool.name for tool in app.list_public_tools()]

    assert "supabase_execute_sql" in public_names
    assert "supabase_health" in public_names
    assert app.token_estimate > 0
    assert app.health_checker is not None


@pytest.mark.asyncio
async def test_health_tool_collision_raises() -> None:
    class HealthUpstream(FakeUpstream):
        def __init__(self) -> None:
            super().__init__()
            self._tools.append(
                ToolSchema(
                    name="health",
                    description="Conflicting tool",
                    input_schema={"type": "object"},
                )
            )

    upstream = HealthUpstream()
    config = ServerConfig(
        name="conflict",
        include_health_tool=True,
        upstream=UpstreamConfig(transport="stdio", stdio_command="fake"),
        rules=AllowRules(allow_patterns=["health"]),
    )

    with pytest.raises(ConfigError, match="collides"):
        await build_server(config, upstream=upstream)
