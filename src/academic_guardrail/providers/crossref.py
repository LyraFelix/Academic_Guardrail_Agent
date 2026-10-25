"""Crossref API Provider with session reuse, Polite Pool headers, retry backoff, and SQLite cache."""

import urllib.parse
from typing import Optional, Dict, Any, List
from academic_guardrail.providers.http_client import AcademicHttpClient
from academic_guardrail.core.cache import get_cache, SqliteCache
from academic_guardrail.core.ref_resolver import ReferenceResolver, add_retraction_evidence
from academic_guardrail.core.exceptions import ProviderError


class CrossrefProvider:
    """Async client for Crossref REST API with session reuse and Polite Pool compliance."""

    BASE_URL = "https://api.crossref.org/works"

    def __init__(
        self,
        email: Optional[str] = "academic-guardrail@example.com",
        client: Optional[AcademicHttpClient] = None,
        cache: Optional[SqliteCache] = None,
    ):
        self.email = email or "academic-guardrail@example.com"
        self.client = client or AcademicHttpClient(email=self.email)
        self.cache = cache or get_cache()

    @staticmethod
    def _process_work(data: Dict[str, Any]) -> Dict[str, Any]:
        """A notice about another paper is not proof this record was retracted."""
        titles = data.get("title", [])
        issued = data.get("issued", {}).get("date-parts", [])
        doi = ReferenceResolver.normalize_doi(data.get("DOI"))
        # Only an explicit relation about this work confirms its retraction.
        relation = data.get("relation", {}).get("is-retracted-by", [])
        confirmed = bool(relation)
        return add_retraction_evidence({
            "title": titles[0] if titles else "",
            "doi": doi,
            "authors": [f"{a.get('given', '')} {a.get('family', '')}".strip()
                        for a in data.get("author", [])],
            "year": issued[0][0] if issued and issued[0] else None,
            "publisher": data.get("publisher"),
            "type": data.get("type"),
            "is_retracted": confirmed,
            "retraction_suspected": data.get("type") in ("retraction", "retraction-notice"),
        }, "Crossref")

    async def get_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        clean_doi = ReferenceResolver.normalize_doi(doi)
        if not clean_doi:
            return None
        cache_key = self.cache.make_key("crossref_doi_v2", clean_doi)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        url = f"{self.BASE_URL}/{urllib.parse.quote(clean_doi, safe='')}"
        response = await self.client.get_json(url)
        if response is None:
            return None
        if not isinstance(response.get("message"), dict):
            raise ProviderError("Crossref returned an invalid work response")
        result = self._process_work(response["message"])
        if result["doi"] != clean_doi:
            raise ProviderError("Crossref returned a different DOI")
        self.cache.set(cache_key, result)
        return result

    async def search_by_title(self, query: str, rows: int = 5) -> List[Dict[str, Any]]:
        cache_key = self.cache.make_key("crossref_title_v2", query, str(rows))
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        url = f"{self.BASE_URL}?query.title={urllib.parse.quote(query)}&rows={rows}"
        response = await self.client.get_json(url)
        if not response or not isinstance(response.get("message", {}).get("items"), list):
            raise ProviderError("Crossref search returned an invalid response")
        results = [self._process_work(item) for item in response["message"]["items"]]
        self.cache.set(cache_key, results)
        return results
