"""Tests for transport detection in upstream module."""

from unittest.mock import MagicMock

import pytest

from mcp_filter.config import ConfigError


class TestTransportDetection:
    """Tests for _connect_stdio transport selection logic.

    Note: Transport class selection is tested implicitly via real integration tests.
    These unit tests focus on input validation and error handling.
    """

    @pytest.mark.asyncio
    async def test_uvx_requires_package_name(self):
        """Test that uvx raises error without package name."""
        from mcp_filter.upstream import _connect_stdio

        mock_fastmcp = MagicMock()

        with pytest.raises(ConfigError, match="uvx transport requires a package name"):
            await _connect_stdio(mock_fastmcp, "uvx", [])

    @pytest.mark.asyncio
    async def test_uv_requires_run_subcommand(self):
        """Test that uv raises error without 'run' subcommand."""
        from mcp_filter.upstream import _connect_stdio

        mock_fastmcp = MagicMock()

        with pytest.raises(ConfigError, match="uv transport requires 'run' subcommand"):
            await _connect_stdio(mock_fastmcp, "uv", ["install", "package"])

    @pytest.mark.asyncio
    async def test_uv_run_requires_script(self):
        """Test that 'uv run' raises error without script name."""
        from mcp_filter.upstream import _connect_stdio

        mock_fastmcp = MagicMock()

        with pytest.raises(ConfigError, match="uv run requires a script or module name"):
            await _connect_stdio(mock_fastmcp, "uv", ["run"])

    @pytest.mark.asyncio
    async def test_uv_with_empty_args_requires_run(self):
        """Test that uv with empty args raises error."""
        from mcp_filter.upstream import _connect_stdio

        mock_fastmcp = MagicMock()

        with pytest.raises(ConfigError, match="uv transport requires 'run' subcommand"):
            await _connect_stdio(mock_fastmcp, "uv", [])
