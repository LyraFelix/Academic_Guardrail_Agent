"""Crossref API Provider with URL quote escaping."""

import urllib.parse
import httpx
from typing import Optional, Dict, Any


class CrossrefProvider:
    """Async client for Crossref REST API."""

    BASE_URL = "https://api.crossref.org/works"

    async def get_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        clean_doi = doi.lower().replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
        quoted_doi = urllib.parse.quote(clean_doi, safe="")
        url = f"{self.BASE_URL}/{quoted_doi}"
        headers = {"User-Agent": "AcademicGuardrail/0.1.0 (mailto:academic-guardrail@example.com)"}
        
        async with httpx.AsyncClient(trust_env=True, timeout=8.0) as client:
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
            except Exception:
                pass
        return None
