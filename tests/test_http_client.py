"""Unit tests for AcademicHttpClient connection pooling & retry behavior."""

import asyncio
from academic_guardrail.providers.http_client import AcademicHttpClient


def test_http_client_initialization():
    async def _test():
        client = AcademicHttpClient(email="test@example.com", timeout=5.0, max_retries=2)
        assert client.email == "test@example.com"
        assert "test@example.com" in client.user_agent
        assert client.timeout == 5.0
        await client.close()
    asyncio.run(_test())


def test_http_client_context_manager():
    async def _test():
        async with AcademicHttpClient(email="test@example.com") as client:
            assert client._client is not None
        assert client._client is None or client._client.is_closed
    asyncio.run(_test())
