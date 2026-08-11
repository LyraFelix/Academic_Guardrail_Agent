"""Unified Async HTTP Client for Academic Guardrail Providers.

Provides session connection pooling, automatic system proxy injection,
Polite Pool User-Agent headers, and exponential backoff retries with full jitter.
"""

import os
import random
import asyncio
import logging
import httpx
from typing import Optional, Dict, Any
from academic_guardrail.core.proxy_detector import SystemProxyDetector
from academic_guardrail.core.exceptions import ProviderError, RateLimitError

logger = logging.getLogger(__name__)


class AcademicHttpClient:
    """Async HTTP Client with connection pooling, proxy detection, and exponential backoff retries."""

    DEFAULT_USER_AGENT = "AcademicGuardrail/0.1.0 (mailto:academic-guardrail@example.com)"

    def __init__(
        self,
        email: Optional[str] = None,
        timeout: float = 12.0,
        max_retries: int = 3,
        max_connections: int = 50,
        max_keepalive_connections: int = 20
    ):
        from academic_guardrail.core.config import GuardrailConfig
        self.email = email or os.environ.get("ACADEMIC_GUARDRAIL_EMAIL") or GuardrailConfig.DEFAULT_EMAIL
        self.timeout = timeout
        self.max_retries = max_retries
        self.user_agent = f"AcademicGuardrail/0.1.0 (mailto:{self.email})"
        
        # Setup connection pool limits
        limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections,
            keepalive_expiry=30.0
        )

        # Detect active proxy
        proxy = SystemProxyDetector.auto_inject_system_proxy()
        client_kwargs = {
            "trust_env": True,
            "timeout": httpx.Timeout(self.timeout),
            "limits": limits,
            "headers": {"User-Agent": self.user_agent}
        }
        if proxy:
            client_kwargs["proxy"] = proxy

        self._client: Optional[httpx.AsyncClient] = httpx.AsyncClient(**client_kwargs)

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            limits = httpx.Limits(
                max_connections=50,
                max_keepalive_connections=20,
                keepalive_expiry=30.0
            )
            proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or os.environ.get("ALL_PROXY")
            client_kwargs = {
                "trust_env": True,
                "timeout": httpx.Timeout(self.timeout),
                "limits": limits,
                "headers": {"User-Agent": self.user_agent}
            }
            if proxy:
                client_kwargs["proxy"] = proxy
            self._client = httpx.AsyncClient(**client_kwargs)
        return self._client

    async def get_json(
        self,
        url: str,
        extra_headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """Executes GET request and parses JSON response with Exponential Backoff + Jitter retries."""
        client = await self.get_client()
        headers = {"User-Agent": self.user_agent}
        if extra_headers:
            headers.update(extra_headers)

        req_timeout = timeout or self.timeout
        base_backoff = 1.0

        for attempt in range(self.max_retries + 1):
            try:
                res = await client.get(url, headers=headers, timeout=req_timeout)
                
                # Success
                if res.status_code == 200:
                    return res.json()
                
                # 404 Not Found is not retried
                if res.status_code == 404:
                    return None

                # Rate Limited (429) or Server Error (502, 503, 504) -> Retry with Backoff
                if res.status_code in (429, 502, 503, 504):
                    if attempt == self.max_retries:
                        if res.status_code == 429:
                            raise RateLimitError(f"API rate limit exceeded (HTTP 429) for {url}")
                        raise ProviderError(f"API server error (HTTP {res.status_code}) for {url}")

                    # Check Retry-After header if present
                    retry_after = res.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        sleep_time = float(retry_after)
                    else:
                        # Full Jitter Exponential Backoff formula: random between 0 and (base * 2^attempt)
                        max_sleep = min(10.0, base_backoff * (2 ** attempt))
                        sleep_time = random.uniform(0.5, max_sleep)

                    logger.warning(f"HTTP {res.status_code} on {url}, retrying in {sleep_time:.2f}s (attempt {attempt + 1}/{self.max_retries})")
                    await asyncio.sleep(sleep_time)
                    continue

                # Unexpected status code
                res.raise_for_status()

            except (httpx.TransportError, httpx.TimeoutException) as e:
                if attempt == self.max_retries:
                    logger.warning(f"Request failed after {self.max_retries} retries: {e}")
                    return None
                max_sleep = min(8.0, base_backoff * (2 ** attempt))
                sleep_time = random.uniform(0.5, max_sleep)
                await asyncio.sleep(sleep_time)

            except (RateLimitError, ProviderError):
                raise
            except Exception as e:
                logger.warning(f"Unexpected error querying {url}: {e}")
                return None

        return None

    async def close(self):
        """Closes the underlying HTTPX AsyncClient session."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
