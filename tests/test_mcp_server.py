"""Unit tests for MCP Server tool handlers and exception middleware."""

import pytest
import asyncio

mcp_mod = pytest.importorskip("mcp.server.fastmcp")

from academic_guardrail.mcp_server import handle_mcp_exceptions
from academic_guardrail.core.exceptions import ProviderError, RateLimitError, ParserError


def test_mcp_tool_exceptions_decorator():
    async def _test():
        @handle_mcp_exceptions
        async def mock_fail_rate_limit():
            raise RateLimitError("429 Too Many Requests")

        @handle_mcp_exceptions
        async def mock_fail_provider():
            raise ProviderError("Connection timeout")

        @handle_mcp_exceptions
        async def mock_fail_parser():
            raise ParserError("Invalid PDF format")

        @handle_mcp_exceptions
        async def mock_file_not_found():
            raise FileNotFoundError("missing.docx")

        res_rl = await mock_fail_rate_limit()
        assert "MCP RATE_LIMIT" in res_rl

        res_pr = await mock_fail_provider()
        assert "MCP PROVIDER_ERROR" in res_pr

        res_pa = await mock_fail_parser()
        assert "MCP PARSER_ERROR" in res_pa

        res_fn = await mock_file_not_found()
        assert "MCP FILE_NOT_FOUND" in res_fn

    asyncio.run(_test())
