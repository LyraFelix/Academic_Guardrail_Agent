"""Unit tests never use personal caches, external APIs or downloaded models."""
import pytest

from academic_guardrail.core import cache, semantic_matcher
from academic_guardrail.core.proxy_detector import SystemProxyDetector


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "_DEFAULT_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(cache, "_global_cache", None)
    monkeypatch.setenv("RETRACTION_DB_PATH", ":memory:")
    monkeypatch.setattr(semantic_matcher, "_HAS_ST", False)
    monkeypatch.setattr(SystemProxyDetector, "probe_local_proxy_ports", lambda: None)
    attempted = []

    async def block_http(self, request, *args, **kwargs):
        attempted.append(request.url.host)
        raise AssertionError("Unit tests must mock provider HTTP responses")

    monkeypatch.setattr("httpx.AsyncClient.send", block_http)
    yield
    assert not attempted, f"Unmocked HTTP requests in unit test: {attempted}"
