"""Crossref API Provider with session reuse, Polite Pool headers, and retry backoff."""

import urllib.parse
from typing import Optional, Dict, Any, List
from academic_guardrail.providers.http_client import AcademicHttpClient


class CrossrefProvider:
    """Async client for Crossref REST API with session reuse and Polite Pool compliance."""

    BASE_URL = "https://api.crossref.org/works"

    def __init__(
        self,
        email: Optional[str] = "academic-guardrail@example.com",
        client: Optional[AcademicHttpClient] = None
    ):
        self.email = email or "academic-guardrail@example.com"
        self.client = client or AcademicHttpClient(email=self.email)

    async def get_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        clean_doi = doi.lower().replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
        quoted_doi = urllib.parse.quote(clean_doi, safe="")
        url = f"{self.BASE_URL}/{quoted_doi}"

        res_json = await self.client.get_json(url)
        if res_json and "message" in res_json:
            data = res_json["message"]
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
        return None

    async def search_by_title(self, query: str, rows: int = 5) -> List[Dict[str, Any]]:
        quoted_q = urllib.parse.quote(query)
        url = f"{self.BASE_URL}?query.title={quoted_q}&rows={rows}"
        res_json = await self.client.get_json(url)
        if res_json and "message" in res_json:
            items = res_json.get("message", {}).get("items", [])
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
                    "doi": item.get("DOI", "").lower() if item.get("DOI") else None,
                    "authors": authors,
                    "year": year,
                    "publisher": item.get("publisher"),
                    "is_retracted": False
                })
            return results
        return []
