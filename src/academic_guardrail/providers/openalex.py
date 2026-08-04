"""OpenAlex API Provider with URL quote escaping and filter fallback."""

import re
import urllib.parse
import httpx
from typing import Optional, Dict, Any


class OpenAlexProvider:
    """Async client for OpenAlex REST API."""

    BASE_URL = "https://api.openalex.org/works"

    def __init__(self, email: Optional[str] = "academic-guardrail@example.com"):
        self.headers = {"User-Agent": f"AcademicGuardrail/0.1.0 (mailto:{email})"}

    async def get_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        clean_doi = doi.lower().replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
        quoted_doi = urllib.parse.quote(clean_doi, safe="")
        url = f"{self.BASE_URL}/https://doi.org/{quoted_doi}"
        async with httpx.AsyncClient(trust_env=True, timeout=8.0) as client:
            try:
                res = await client.get(url, headers=self.headers)
                if res.status_code == 200:
                    return self._process_work(res.json())
                
                # Check for arXiv DOI format
                arxiv_match = re.search(r'\d{4}\.\d{4,5}', clean_doi)
                if arxiv_match:
                    arxiv_id = arxiv_match.group(0)
                    url_arxiv = f"{self.BASE_URL}?search={arxiv_id}&per_page=1"
                    res_ax = await client.get(url_arxiv, headers=self.headers)
                    if res_ax.status_code == 200:
                        data_ax = res_ax.json()
                        results = data_ax.get("results", [])
                        if results:
                            return self._process_work(results[0])
            except Exception:
                pass
        return None

    async def search_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        clean_query = title.replace("[J]", "").replace("[M]", "").replace("[D]", "").replace("[C]", "").strip()
        url = f"{self.BASE_URL}?search={urllib.parse.quote(clean_query)}&per_page=3"
        async with httpx.AsyncClient(trust_env=True, timeout=8.0) as client:
            try:
                res = await client.get(url, headers=self.headers)
                if res.status_code == 200:
                    data = res.json()
                    results = data.get("results", [])
                    if results:
                        return self._process_work(results[0])
            except Exception:
                pass
        return None

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

        doi = work.get("doi")
        if doi:
            doi = doi.replace("https://doi.org/", "").lower()

        title = work.get("title") or work.get("display_name") or ""
        authorships = work.get("authorships", [])
        authors = [a.get("author", {}).get("display_name") for a in authorships if a.get("author")]

        is_retracted = work.get("is_retracted", False) or ("retracted" in title.lower()) or (work.get("type") == "retraction-notice")

        return {
            "title": title,
            "doi": doi,
            "publication_year": work.get("publication_year"),
            "authors": authors,
            "abstract": abstract,
            "is_retracted": is_retracted,
            "openalex_id": work.get("id"),
            "cited_by_count": work.get("cited_by_count", 0)
        }
