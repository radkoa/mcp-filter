"""Fake upstream MCP server used for tests."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from mcp_filter.upstream import ToolSchema, Upstream


class FakeUpstream(Upstream):
    """In-process upstream that records tool calls."""

    def __init__(self) -> None:
        self._tools: List[ToolSchema] = [
            ToolSchema(
                name="execute_sql",
                description="Execute a SQL query and return the results.",
                input_schema={
                    "type": "object",
                    "properties": {"sql": {"type": "string", "description": "SQL query"}},
                    "required": ["sql"],
                },
            ),
            ToolSchema(
                name="create_project",
                description="Create a new project.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Project name"},
                        "region": {"type": "string", "description": "Cloud region"},
                    },
                    "required": ["name", "region"],
                },
            ),
            ToolSchema(
                name="delete_branch",
                description="Delete a git branch.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "branch": {"type": "string", "description": "Branch to delete"}
                    },
                    "required": ["branch"],
                },
            ),
        ]
        self.calls: List[Tuple[str, Dict[str, Any]]] = []

    async def list_tools(self) -> List[ToolSchema]:
        return list(self._tools)

    async def call_tool(self, name: str, args: Dict[str, Any]) -> Any:
        self.calls.append((name, args))
        if name == "execute_sql":
            sql = args.get("sql", "")
            return {"content": [{"type": "text", "text": f"Query executed: {sql}"}]}
        if name == "create_project":
            return {
                "content": [
                    {"type": "text", "text": f"Project created: {args.get('name', '')}"}
                ]
            }
        if name == "delete_branch":
            return {
                "content": [
                    {"type": "text", "text": f"Branch deleted: {args.get('branch', '')}"}
                ]
            }
        return {
            "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
            "isError": True,
        }
