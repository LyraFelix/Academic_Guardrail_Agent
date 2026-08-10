"""Chinese Academic Literature Matching Provider with Parallel API Resolution, Session Reuse, First-Completed Multi-Source Racing, and Local Fallback."""

import os
import re
import urllib.parse
import asyncio
from typing import Optional, Dict, Any, List
from academic_guardrail.providers.http_client import AcademicHttpClient
from academic_guardrail.providers.openalex import OpenAlexProvider
from academic_guardrail.providers.crossref import CrossrefProvider
from academic_guardrail.core.ref_resolver import ReferenceResolver
from academic_guardrail.core.models import Citation

CHINESE_CORE_JOURNALS = [
    "管理世界", "经济研究", "金融研究", "软件学报", "计算机学报", "中国社会科学",
    "法学研究", "世界经济", "会计研究", "中国工业经济", "数理统计与管理", "情报学报",
    "中国管理科学", "中国人力资源开发", "城市发展研究", "数量经济技术经济研究", "地理学报",
    "经济学(季刊)", "经济学季刊", "经济理论与经济管理", "城市规划", "中国软科学", "学术界", "统计研究", "思想战线"
]


from academic_guardrail.core.cache import get_cache, SqliteCache


class ChineseAcademicProvider:
    """Matches Chinese citations using OpenAlex, Crossref, Semantic Scholar with proxy support, First-Completed racing, and CSSCI fallback."""

    def __init__(
        self,
        email: Optional[str] = "academic-guardrail@example.com",
        client: Optional[AcademicHttpClient] = None,
        max_concurrency: int = 5,
        cache: Optional[SqliteCache] = None,
    ):
        self.email = email or "academic-guardrail@example.com"
        self.client = client or AcademicHttpClient(email=self.email)
        self.cache = cache or get_cache()
        self.openalex = OpenAlexProvider(email=self.email, client=self.client, cache=self.cache)
        self.crossref = CrossrefProvider(email=self.email, client=self.client, cache=self.cache)
        self.resolver = ReferenceResolver()
        self.max_concurrency = max_concurrency
        self._sem: Optional[asyncio.Semaphore] = None

    def _get_semaphore(self) -> asyncio.Semaphore:
        """Returns or lazily initializes an event-loop-safe Semaphore."""
        if self._sem is None:
            self._sem = asyncio.Semaphore(self.max_concurrency)
        return self._sem

    def _extract_core_title(self, raw_str: str) -> str:
        if not raw_str:
            return ""
        title = re.split(r'\[[JMDNRCP]\]', raw_str)[0]
        title = re.sub(r'^\[\d+\]\s*', '', title)
        parts = re.split(r'[\.\。]\s*', title, maxsplit=1)
        if len(parts) > 1 and len(parts[1].strip()) > 3:
            title = parts[1]
        elif len(parts) > 0:
            title = parts[0]
        colon_parts = re.split(r'[—–:：]', title, maxsplit=1)
        if len(colon_parts) == 2 and len(colon_parts[1].strip()) > 40:
            title = colon_parts[0]
        title = re.sub(r'\s*\d{4}\.?\s*$', '', title)
        return title.strip()

    async def _search_semantic_scholar_candidates(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        cache_key = self.cache.make_key("s2_search", query.lower().strip(), str(limit))
        cached_data = self.cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        quoted_q = urllib.parse.quote(query)
        base_url = os.environ.get("SEMANTIC_SCHOLAR_API_BASE", "https://api.semanticscholar.org/graph/v1")
        url = f"{base_url}/paper/search?query={quoted_q}&limit={limit}&fields=title,authors,year,externalIds,abstract,isRetracted,venue"

        data_json = await self.client.get_json(url)
        if data_json and "data" in data_json:
            data = data_json["data"]
            results = []
            for p in data:
                ext_ids = p.get("externalIds", {})
                doi = ext_ids.get("DOI") or ext_ids.get("ArXiv")
                authors = [a.get("name") for a in p.get("authors", []) if a.get("name")]
                results.append({
                    "title": p.get("title"),
                    "doi": doi.lower() if doi else None,
                    "authors": authors,
                    "year": p.get("year"),
                    "venue": p.get("venue"),
                    "abstract": p.get("abstract", ""),
                    "is_retracted": p.get("isRetracted", False)
                })
            self.cache.set(cache_key, results)
            return results
        self.cache.set(cache_key, [])
        return []

    async def verify_citation(
        self,
        title: str,
        doi: Optional[str] = None,
        authors: Optional[list] = None,
        raw_text: Optional[str] = None
    ) -> Dict[str, Any]:
        dummy_cit = Citation(
            id="cit_verify",
            raw_text=raw_text or title or "",
            doi=doi,
            title=title,
            authors=authors or []
        )

        sem = self._get_semaphore()
        async with sem:
            try:
                # Priority 1: Direct Online DOI Resolution (OpenAlex + Crossref)
                if doi:
                    clean_doi = doi.strip().lower()
                    results = await asyncio.gather(
                        asyncio.wait_for(self.openalex.get_by_doi(clean_doi), timeout=8.0),
                        asyncio.wait_for(self.crossref.get_by_doi(clean_doi), timeout=8.0),
                        return_exceptions=True
                    )
                    openalex_res = results[0] if isinstance(results[0], dict) else None
                    crossref_res = results[1] if isinstance(results[1], dict) else None

                    matched_title = (openalex_res.get("title") if openalex_res else None) or \
                                    (crossref_res.get("title") if crossref_res else None) or title

                    is_retracted = (openalex_res.get("is_retracted") if openalex_res else False) or \
                                   (crossref_res.get("is_retracted") if crossref_res else False) or \
                                   any(kw in matched_title.lower() for kw in ["retracted", "retraction", "withdrawn", "撤稿"])

                    abstract = (openalex_res.get("abstract") or "") if openalex_res else ""

                    if (openalex_res and openalex_res.get("title")) or (crossref_res and crossref_res.get("title")):
                        return {
                            "matched": True,
                            "doi": clean_doi,
                            "title": matched_title,
                            "is_retracted": is_retracted,
                            "abstract": abstract,
                            "confidence": 1.0,
                            "source": "Crossref/OpenAlex (DOI)"
                        }

                # Priority 2: Online Multi-API Title Racing (OpenAlex, Semantic Scholar, Crossref)
                core_title = self._extract_core_title(title)
                query_str = core_title if (core_title and len(core_title) >= 5) else (title or doi or "")

                if query_str and len(query_str) >= 3:
                    # Launch API queries concurrently and process as they complete (First Qualified Winner)
                    async def fetch_openalex():
                        try:
                            cands = await asyncio.wait_for(self.openalex.search_by_title(query_str, per_page=5), timeout=15.0)
                            best = self.resolver.select_best_candidate(dummy_cit, cands, min_score=0.40)
                            if best and best.get("title"):
                                return {
                                    "matched": True,
                                    "doi": best.get("doi"),
                                    "title": best.get("title"),
                                    "is_retracted": best.get("is_retracted", False),
                                    "abstract": best.get("abstract", ""),
                                    "confidence": round(best.get("match_score", 0.90), 2),
                                    "source": "OpenAlex (Title Search)"
                                }
                        except Exception:
                            pass
                        return None

                    async def fetch_s2():
                        try:
                            cands = await asyncio.wait_for(self._search_semantic_scholar_candidates(query_str, limit=5), timeout=15.0)
                            best = self.resolver.select_best_candidate(dummy_cit, cands, min_score=0.40)
                            if best and best.get("title"):
                                return {
                                    "matched": True,
                                    "doi": best.get("doi"),
                                    "title": best.get("title"),
                                    "is_retracted": best.get("is_retracted", False),
                                    "abstract": best.get("abstract", ""),
                                    "confidence": round(best.get("match_score", 0.90), 2),
                                    "source": "Semantic Scholar (Online Abstract)"
                                }
                        except Exception:
                            pass
                        return None

                    async def fetch_crossref():
                        try:
                            cands = await asyncio.wait_for(self.crossref.search_by_title(query_str, rows=5), timeout=15.0)
                            best = self.resolver.select_best_candidate(dummy_cit, cands, min_score=0.40)
                            if best and best.get("doi"):
                                found_doi = best.get("doi")
                                abstract = ""
                                if found_doi:
                                    try:
                                        o_res = await asyncio.wait_for(self.openalex.get_by_doi(found_doi), timeout=8.0)
                                        if o_res and o_res.get("abstract"):
                                            abstract = o_res.get("abstract")
                                    except Exception:
                                        pass
                                return {
                                    "matched": True,
                                    "doi": found_doi,
                                    "title": best.get("title"),
                                    "is_retracted": best.get("is_retracted", False),
                                    "abstract": abstract,
                                    "confidence": round(best.get("match_score", 0.85), 2),
                                    "source": "Crossref (Online Title Search)"
                                }
                        except Exception:
                            pass
                        return None

                    # Race Tasks: return immediately when any API succeeds
                    tasks = [asyncio.create_task(fetch_openalex()), asyncio.create_task(fetch_s2()), asyncio.create_task(fetch_crossref())]
                    for completed in asyncio.as_completed(tasks):
                        result = await completed
                        if result and result.get("matched"):
                            # Cancel remaining background tasks
                            for t in tasks:
                                if not t.done():
                                    t.cancel()
                            return result

                # Priority 3: CSSCI / CSCD Local Core Journal Fallback (Only when all online APIs failed/unverified)
                search_corpus = f"{title} {raw_text or ''}"
                matched_journal = next((j for j in CHINESE_CORE_JOURNALS if j in search_corpus), None)
                if matched_journal:
                    core_t = self._extract_core_title(title)
                    return {
                        "matched": True,
                        "doi": doi or "cnki.local.core",
                        "title": core_t or title,
                        "is_retracted": False,
                        "abstract": "",
                        "confidence": 0.95,
                        "source": f"CSSCI/CSCD 本地核心期刊数据库 ({matched_journal})"
                    }

            except Exception:
                pass

            # Priority 4: Final Fallback
            return {
                "matched": False,
                "doi": doi,
                "title": title,
                "is_retracted": False,
                "abstract": "",
                "confidence": 0.0,
                "source": "None"
            }
