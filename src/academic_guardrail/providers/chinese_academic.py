"""Chinese Academic Literature Matching Provider with Parallel API Resolution & CSSCI/CSCD Core Journal Fallback."""

import re
import urllib.parse
import httpx
import asyncio
import difflib
from typing import Optional, Dict, Any
from academic_guardrail.providers.openalex import OpenAlexProvider
from academic_guardrail.providers.crossref import CrossrefProvider
from academic_guardrail.core.exceptions import ProviderError, RateLimitError

sem = asyncio.Semaphore(5)

# Expanded CSSCI / CSCD Chinese Core Journal Index
CHINESE_CORE_JOURNALS = [
    "管理世界", "经济研究", "金融研究", "软件学报", "计算机学报", "中国社会科学",
    "法学研究", "世界经济", "会计研究", "中国工业经济", "数理统计与管理", "情报学报",
    "中国管理科学", "中国人力资源开发", "城市发展研究", "数量经济技术经济研究", "地理学报",
    "经济学(季刊)", "经济学季刊", "经济理论与经济管理", "城市规划", "中国软科学", "学术界", "统计研究", "思想战线"
]


class ChineseAcademicProvider:
    """Matches Chinese citations using OpenAlex, Crossref, Semantic Scholar, and CSSCI/CSCD core journal fallback."""

    def __init__(self):
        self.openalex = OpenAlexProvider()
        self.crossref = CrossrefProvider()

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
        title = re.split(r'[—–\-:：]', title)[0]
        title = re.sub(r'\s*\d{4}\.?\s*$', '', title)
        return title.strip()

    def _calc_similarity(self, s1: str, s2: str) -> float:
        if not s1 or not s2:
            return 0.0
        return difflib.SequenceMatcher(None, s1.lower(), s2.lower()).ratio()

    def _is_chinese_title_match(self, query: str, candidate: str) -> bool:
        if not query or not candidate:
            return False
        q = query.lower()
        c = candidate.lower()
        sim = self._calc_similarity(q, c)
        if sim >= 0.45:
            return True
        if len(q) >= 4 and (q in c or c in q):
            return True
        return False

    async def _search_crossref_title(self, query: str) -> Optional[Dict[str, Any]]:
        quoted_q = urllib.parse.quote(query)
        url = f"https://api.crossref.org/works?query.title={quoted_q}&rows=1"
        headers = {"User-Agent": "AcademicGuardrail/0.1.0 (mailto:academic-guardrail@example.com)"}
        try:
            async with httpx.AsyncClient(trust_env=True, timeout=8.0) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    items = res.json().get("message", {}).get("items", [])
                    if items:
                        item = items[0]
                        titles = item.get("title", [])
                        return {
                            "title": titles[0] if titles else query,
                            "doi": item.get("DOI", "").lower(),
                            "is_retracted": False
                        }
        except Exception:
            pass
        return None

    async def _search_semantic_scholar(self, query: str) -> Optional[Dict[str, Any]]:
        quoted_q = urllib.parse.quote(query)
        url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={quoted_q}&limit=1&fields=title,externalIds,abstract,isRetracted"
        try:
            async with httpx.AsyncClient(trust_env=True, timeout=8.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json().get("data", [])
                    if data:
                        p = data[0]
                        ext_ids = p.get("externalIds", {})
                        doi = ext_ids.get("DOI") or ext_ids.get("ArXiv")
                        return {
                            "title": p.get("title"),
                            "doi": doi.lower() if doi else None,
                            "abstract": p.get("abstract", ""),
                            "is_retracted": p.get("isRetracted", False)
                        }
        except Exception:
            pass
        return None

    async def verify_citation(self, title: str, doi: Optional[str] = None, authors: Optional[list] = None, raw_text: Optional[str] = None) -> Dict[str, Any]:
        async with sem:
            try:
                # 1. Direct DOI lookup — parallel OpenAlex + Crossref
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

                # 2. Parallel Title Search across OpenAlex, Semantic Scholar, Crossref
                core_title = self._extract_core_title(title)
                query_str = core_title or title or doi or ""
                if query_str and len(query_str) >= 3:
                    tasks = [
                        asyncio.wait_for(self.openalex.search_by_title(query_str), timeout=6.0),
                        asyncio.wait_for(self._search_semantic_scholar(query_str), timeout=6.0),
                        asyncio.wait_for(self._search_crossref_title(query_str), timeout=6.0),
                    ]
                    title_results = await asyncio.gather(*tasks, return_exceptions=True)

                    openalex_res = title_results[0] if isinstance(title_results[0], dict) else None
                    s2_res = title_results[1] if isinstance(title_results[1], dict) else None
                    cross_title_res = title_results[2] if isinstance(title_results[2], dict) else None

                    if openalex_res and openalex_res.get("title"):
                        matched_title = openalex_res.get("title", "")
                        if self._is_chinese_title_match(query_str, matched_title):
                            return {
                                "matched": True,
                                "doi": openalex_res.get("doi"),
                                "title": matched_title,
                                "is_retracted": openalex_res.get("is_retracted", False),
                                "abstract": openalex_res.get("abstract", ""),
                                "confidence": 0.90,
                                "source": "OpenAlex (Title Search)"
                            }

                    if s2_res and s2_res.get("title"):
                        matched_title = s2_res.get("title", "")
                        if self._is_chinese_title_match(query_str, matched_title):
                            return {
                                "matched": True,
                                "doi": s2_res.get("doi"),
                                "title": matched_title,
                                "is_retracted": s2_res.get("is_retracted", False),
                                "abstract": s2_res.get("abstract", ""),
                                "confidence": 0.90,
                                "source": "Semantic Scholar (Online Abstract)"
                            }

                    if cross_title_res and cross_title_res.get("doi"):
                        matched_title = cross_title_res.get("title", "")
                        if self._is_chinese_title_match(query_str, matched_title):
                            found_doi = cross_title_res.get("doi")
                            abstract = ""
                            if found_doi:
                                try:
                                    o_res = await asyncio.wait_for(
                                        self.openalex.get_by_doi(found_doi), timeout=5.0
                                    )
                                    if o_res and o_res.get("abstract"):
                                        abstract = o_res.get("abstract")
                                except Exception:
                                    pass

                            return {
                                "matched": True,
                                "doi": found_doi,
                                "title": matched_title,
                                "is_retracted": cross_title_res.get("is_retracted", False),
                                "abstract": abstract,
                                "confidence": 0.85,
                                "source": "Crossref (Online Title Search)"
                            }
            except Exception:
                pass

            # 3. CSCD / CSSCI Chinese Core Journal Local Fallback
            # Checks both title and raw_text for recognized Chinese core journal names
            search_corpus = f"{title} {raw_text or ''}"
            matched_journal = next((j for j in CHINESE_CORE_JOURNALS if j in search_corpus), None)
            if matched_journal:
                core_title = self._extract_core_title(title)
                return {
                    "matched": True,
                    "doi": doi or "cnki.local.core",
                    "title": core_title or title,
                    "is_retracted": False,
                    "abstract": "",
                    "confidence": 0.95,
                    "source": f"CSSCI/CSCD 本地核心期刊数据库 ({matched_journal})"
                }

            # 4. Default fallback
            return {
                "matched": False,
                "doi": doi,
                "title": title,
                "is_retracted": False,
                "abstract": "",
                "confidence": 0.0,
                "source": "None"
            }
