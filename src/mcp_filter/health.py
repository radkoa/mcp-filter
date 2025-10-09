"""Health reporting helpers for the filter server."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Sequence

from .upstream import Upstream

logger = logging.getLogger(__name__)


def estimate_tokens(tool_documents: Iterable[Dict[str, Any]]) -> int:
    """Rough token estimate based on JSON length (4 chars ≈ 1 token)."""

    total_chars = 0
    for document in tool_documents:
        total_chars += len(json.dumps(document, sort_keys=True))
    return total_chars // 4


@dataclass
class HealthChecker:
    """Encapsulates health status computation for the filter server."""

    upstream: Upstream
    exposed_tools: Sequence[str]
    token_estimate: int

    async def report(self) -> Dict[str, Any]:
        """Return structured health information (safe for exposure)."""

        try:
            await self.upstream.list_tools()
            upstream_ok = True
        except Exception:  # pragma: no cover - defensive log branch
            upstream_ok = False
            logger.exception("Upstream health probe failed.")

        return {
            "upstream_ok": upstream_ok,
            "exposed_tools": sorted(self.exposed_tools),
            "tool_count": len(self.exposed_tools),
            "token_estimate": self.token_estimate,
        }

    async def handle(self, _: Dict[str, Any]) -> list[Dict[str, Any]]:
        """MCP Server-compatible handler wrapper.

        Returns a list of content items (as expected by MCP Server's call_tool handler).
        """
        report = await self.report()
        # Return in MCP content format: list of text content items
        return [{"type": "text", "text": self.to_json(report)}]

    @staticmethod
    def to_json(report: Dict[str, Any]) -> str:
        """Render a report as pretty JSON text."""

        return json.dumps(report, indent=2, sort_keys=True)
