import os
import urllib.parse
import httpx
from typing import Optional, Dict, Any, List
from academic_guardrail.core.exceptions import ProviderError, RateLimitError


class CrossrefProvider:
    """Async client for Crossref REST API."""

    BASE_URL = "https://api.crossref.org/works"

    async def get_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        clean_doi = doi.lower().replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
        quoted_doi = urllib.parse.quote(clean_doi, safe="")
        url = f"{self.BASE_URL}/{quoted_doi}"
        headers = {"User-Agent": "AcademicGuardrail/0.1.0 (mailto:academic-guardrail@example.com)"}
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or os.environ.get("ALL_PROXY")
        client_kw = {"trust_env": True, "timeout": 12.0}
        if proxy:
            client_kw["proxy"] = proxy

        async with httpx.AsyncClient(**client_kw) as client:
            try:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    data = res.json().get("message", {})

                    update_to = data.get("update-to", [])
                    is_update_retracted = any(item.get("type") == "retraction" for item in update_to)

                    title_list = data.get("title", [])
                    title = title_list[0] if title_list else ""

                    is_title_retracted = "retracted" in title.lower() or "retraction" in title.lower()
                    is_type_retracted = data.get("type") in ["retraction", "retraction-notice"]

                    is_retracted = is_update_retracted or is_title_retracted or is_type_retracted

                    return {
                        "title": title,
                        "doi": clean_doi,
                        "publisher": data.get("publisher"),
                        "is_retracted": is_retracted,
                        "type": data.get("type")
                    }
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    raise RateLimitError("Crossref API rate limit exceeded (HTTP 429)") from e
                raise ProviderError(f"Crossref HTTP error: {e}") from e
            except httpx.RequestError as e:
                raise ProviderError(f"Crossref network error: {e}") from e
            except Exception as e:
                raise ProviderError(f"Crossref unexpected error: {e}") from e
        return None

    async def search_by_title(self, query: str, rows: int = 5) -> List[Dict[str, Any]]:
        quoted_q = urllib.parse.quote(query)
        url = f"{self.BASE_URL}?query.title={quoted_q}&rows={rows}"
        headers = {"User-Agent": "AcademicGuardrail/0.1.0 (mailto:academic-guardrail@example.com)"}
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or os.environ.get("ALL_PROXY")
        client_kw = {"trust_env": True, "timeout": 12.0}
        if proxy:
            client_kw["proxy"] = proxy
        try:
            async with httpx.AsyncClient(**client_kw) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    items = res.json().get("message", {}).get("items", [])
                    results = []
                    for item in items:
                        titles = item.get("title", [])
                        t = titles[0] if titles else query
                        authors_raw = item.get("author", [])
                        authors = [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in authors_raw]
                        year = None
                        issued = item.get("issued", {}).get("date-parts", [])
                        if issued and issued[0]:
                            year = issued[0][0]

                        results.append({
                            "title": t,
                            "doi": item.get("DOI", "").lower(),
                            "authors": authors,
                            "year": year,
                            "publisher": item.get("publisher"),
                            "is_retracted": False
                        })
                    return results
        except Exception:
            pass
        return []
