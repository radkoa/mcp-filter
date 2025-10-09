"""Filter MCP server implementation."""

from __future__ import annotations

import logging
import re
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Mapping, Optional

from pydantic import BaseModel

from .config import AllowRules, ConfigError, ServerConfig
from .health import HealthChecker, estimate_tokens
from .logging import set_log_context, setup_logging
from .upstream import ToolSchema, Upstream, make_upstream

logger = logging.getLogger(__name__)


class ExposedTool(BaseModel):
    """Represents a tool published by the filter server."""

    public_name: str
    upstream_name: str
    description: str
    input_schema: Dict[str, Any]

    model_config = {"arbitrary_types_allowed": True}


class FilterApplication:
    """In-memory representation of the filter server."""

    def __init__(
        self,
        config: ServerConfig,
        upstream: Upstream,
        tools: List[ExposedTool],
        token_estimate: int,
        local_handlers: Optional[Mapping[str, Callable[[Dict[str, Any]], Awaitable[Any]]]] = None,
        health_checker: Optional[HealthChecker] = None,
    ) -> None:
        self.config = config
        self.upstream = upstream
        self.exposed_tools = tools
        self.token_estimate = token_estimate
        self._local_handlers = dict(local_handlers or {})
        self._tool_map = {tool.public_name: tool for tool in tools}
        self._fastmcp_app: Any | None = None
        self.health_checker = health_checker

    def list_public_tools(self) -> List[ToolSchema]:
        """Return metadata for all tools exposed by the filter."""

        return [
            ToolSchema(
                name=tool.public_name,
                description=tool.description,
                input_schema=tool.input_schema,
            )
            for tool in self.exposed_tools
        ]

    async def call_tool(self, name: str, args: Dict[str, Any]) -> Any:
        """Forward a tool call to the upstream or handle it locally."""

        if name not in self._tool_map:
            raise ConfigError(f"Tool '{name}' is not exposed by this filter.")

        tool = self._tool_map[name]
        _validate_arguments(tool.input_schema, args)

        if name in self._local_handlers:
            return await self._local_handlers[name](args)

        return await self.upstream.call_tool(tool.upstream_name, args)

    def ensure_fastmcp_app(self) -> Any:
        """Instantiate and memoize the actual MCP Server instance."""

        if self._fastmcp_app is not None:
            return self._fastmcp_app

        try:
            from mcp.server import Server
            from mcp.types import Tool
        except ImportError as exc:  # pragma: no cover - optional dependency in tests
            raise ConfigError(
                "mcp is required to run the server. Install with `pip install mcp`."
            ) from exc

        server = Server(self.config.name)

        # Register list_tools handler
        @server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            return [
                Tool(
                    name=tool.public_name,
                    description=tool.description,
                    inputSchema=tool.input_schema,
                )
                for tool in self.exposed_tools
            ]

        # Register call_tool handler
        @server.call_tool()
        async def handle_call_tool(name: str, arguments: dict[str, Any]) -> Any:
            return await self.call_tool(name, arguments)

        self._fastmcp_app = server
        return server

    async def run(self) -> None:
        """Run the MCP server on stdio."""

        server = self.ensure_fastmcp_app()

        # Use MCP's stdio_server to get streams and run
        try:
            from mcp.server.stdio import stdio_server
        except ImportError as exc:
            raise ConfigError("mcp.server.stdio is required") from exc

        async with stdio_server() as (read_stream, write_stream):
            # Get init options (empty for now, could be extended)
            init_options = server.create_initialization_options()
            await server.run(read_stream, write_stream, init_options)

def filter_tools(upstream_tools: List[ToolSchema], rules: AllowRules) -> List[ExposedTool]:
    """Filter the upstream tool list based on the configured rules."""

    if not upstream_tools:
        return []

    allowed: List[ToolSchema] = []

    if rules.allow_tools:
        allowed_names = set(rules.allow_tools)
        allowed = [tool for tool in upstream_tools if tool.name in allowed_names]
    elif rules.allow_patterns:
        pattern_compiled = [_compile_pattern(pat) for pat in rules.allow_patterns]
        allowed = [
            tool for tool in upstream_tools if _matches_any(tool.name, pattern_compiled)
        ]
    else:
        allowed = list(upstream_tools)

    if rules.deny_patterns:
        deny_compiled = [_compile_pattern(pat) for pat in rules.deny_patterns]
        allowed = [
            tool for tool in allowed if not _matches_any(tool.name, deny_compiled)
        ]

    if not allowed:
        raise ConfigError("No tools remain after applying allow/deny rules.")

    rename_prefix = rules.rename_prefix or ""
    seen: Dict[str, str] = {}
    exposed: List[ExposedTool] = []

    for tool in allowed:
        public_name = f"{rename_prefix}{tool.name}"
        if public_name in seen:
            conflict = seen[public_name]
            raise ConfigError(
                f"Tool name collision detected for '{public_name}' (from '{conflict}' and '{tool.name}')."
            )
        seen[public_name] = tool.name
        exposed.append(
            ExposedTool(
                public_name=public_name,
                upstream_name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
            )
        )

    return exposed


async def build_server(
    cfg: ServerConfig,
    upstream: Optional[Upstream] = None,
) -> FilterApplication:
    """Build the filter server application."""

    setup_logging(cfg.log_level)
    upstream_client = upstream or await make_upstream(cfg.upstream)

    upstream_tools = await upstream_client.list_tools()
    exposed = filter_tools(upstream_tools, cfg.rules)
    filtered_docs = [
        {
            "name": tool.public_name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for tool in exposed
    ]
    token_estimate = estimate_tokens(filtered_docs) if cfg.show_token_estimates else 0

    local_handlers: Dict[str, Callable[[Dict[str, Any]], Awaitable[Any]]] = {}
    health_checker: Optional[HealthChecker] = None
    if cfg.include_health_tool:
        base_health_name = "health"
        health_name = (
            f"{cfg.rules.rename_prefix}{base_health_name}"
            if cfg.rules.rename_prefix
            else base_health_name
        )
        if any(tool.public_name == health_name for tool in exposed):
            raise ConfigError(
                f"Health tool name '{health_name}' collides with an exposed upstream tool."
            )
        health_checker = HealthChecker(
            upstream=upstream_client,
            exposed_tools=[tool.public_name for tool in exposed],
            token_estimate=token_estimate,
        )
        health_tool = ExposedTool(
            public_name=health_name,
            upstream_name="__health__",
            description="Report upstream availability and exposed tool summary.",
            input_schema={"type": "object", "properties": {}, "required": []},
        )
        exposed.append(health_tool)
        local_handlers[health_name] = health_checker.handle

    set_log_context(
        server_name=cfg.name,
        upstream_transport=cfg.upstream.transport,
        allowed_tools=len(exposed),
    )

    logger.info("Filter server initialized.")
    if token_estimate:
        logger.info("Approximate token budget for tool metadata: %s", token_estimate)

    return FilterApplication(
        config=cfg,
        upstream=upstream_client,
        tools=exposed,
        token_estimate=token_estimate,
        local_handlers=local_handlers,
        health_checker=health_checker,
    )


def _matches_any(name: str, patterns: Iterable[re.Pattern[str]]) -> bool:
    return any(pattern.search(name) for pattern in patterns)


def _compile_pattern(pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise ConfigError(f"Invalid regex pattern '{pattern}': {exc}") from exc


def _validate_arguments(schema: Mapping[str, Any], args: Mapping[str, Any]) -> None:
    if not isinstance(args, Mapping):
        raise ConfigError("Tool arguments must be a JSON object.")

    required = schema.get("required", []) if isinstance(schema, Mapping) else []
    for key in required:
        if key not in args:
            raise ConfigError(f"Missing required argument '{key}'.")

    if schema.get("type") == "object":
        properties = schema.get("properties", {})
        if isinstance(properties, Mapping):
            allowed_keys = set(properties.keys())
            additional_allowed = schema.get("additionalProperties", True)
            if not additional_allowed:
                extras = set(args.keys()) - allowed_keys
                if extras:
                    raise ConfigError(
                        "Arguments contain disallowed fields: "
                        + ", ".join(sorted(extras))
                    )
