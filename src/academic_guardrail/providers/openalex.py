"""OpenAlex API Provider with URL quote escaping, session reuse, retry backoff, and SQLite cache."""

import urllib.parse
from typing import Optional, Dict, Any, List
from academic_guardrail.providers.http_client import AcademicHttpClient
from academic_guardrail.core.cache import get_cache, SqliteCache
from academic_guardrail.core.ref_resolver import ReferenceResolver, add_retraction_evidence
from academic_guardrail.core.exceptions import ProviderError


class OpenAlexProvider:
    """Async client for OpenAlex REST API with session reuse and Polite Pool compliance."""

    BASE_URL = "https://api.openalex.org/works"

    def __init__(
        self,
        email: Optional[str] = "academic-guardrail@example.com",
        client: Optional[AcademicHttpClient] = None,
        cache: Optional[SqliteCache] = None,
    ):
        self.email = email or "academic-guardrail@example.com"
        self.client = client or AcademicHttpClient(email=self.email)
        self.cache = cache or get_cache()

    async def get_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        clean_doi = ReferenceResolver.normalize_doi(doi)
        if not clean_doi:
            return None

        # --- Cache check ---
        cache_key = self.cache.make_key("openalex_doi_v2", clean_doi)
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        quoted_doi = urllib.parse.quote(clean_doi, safe="")
        url = f"{self.BASE_URL}/{quoted_doi}"

        data = await self.client.get_json(url)
        if data is not None:
            if not isinstance(data, dict) or not data.get("doi"):
                raise ProviderError("OpenAlex returned an invalid work response")
            result = self._process_work(data)
            if result.get("doi") != clean_doi:
                raise ProviderError("OpenAlex returned a different DOI")
            self.cache.set(cache_key, result)
            return result

        return None

    async def search_by_title(self, title: str, per_page: int = 5) -> List[Dict[str, Any]]:
        clean_query = title.replace("[J]", "").replace("[M]", "").replace("[D]", "").replace("[C]", "").strip()

        # --- Cache check ---
        cache_key = self.cache.make_key("openalex_title_v2", clean_query, str(per_page))
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        url = f"{self.BASE_URL}?search={urllib.parse.quote(clean_query)}&per_page={per_page}"
        data = await self.client.get_json(url)
        if data and "results" in data:
            results = [self._process_work(item) for item in data["results"]]
            self.cache.set(cache_key, results)
            return results
        raise ProviderError("OpenAlex search returned an invalid response")

    def _process_work(self, work: Dict[str, Any]) -> Dict[str, Any]:
        abstract = ""
        inv_index = work.get("abstract_inverted_index")
        if inv_index:
            word_positions = []
            for word, positions in inv_index.items():
                for pos in positions:
                    word_positions.append((pos, word))
            word_positions.sort(key=lambda x: x[0])
            abstract = " ".join([w for _, w in word_positions])

        doi = ReferenceResolver.normalize_doi(work.get("doi"))

        title = work.get("title") or work.get("display_name") or ""
        authorships = work.get("authorships", [])
        authors = [a.get("author", {}).get("display_name") for a in authorships if a.get("author")]

        return add_retraction_evidence({
            "title": title,
            "doi": doi,
            "publication_year": work.get("publication_year"),
            "authors": authors,
            "abstract": abstract,
            "is_retracted": work.get("is_retracted"),
            "openalex_id": work.get("id"),
            "cited_by_count": work.get("cited_by_count", 0)
        }, "OpenAlex")
