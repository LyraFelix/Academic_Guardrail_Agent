"""Collect citation candidates and source observations from bounded parallel queries."""

import os
import re
import logging
import urllib.parse
import asyncio
from typing import Optional, Dict, Any, List
from academic_guardrail.providers.http_client import AcademicHttpClient
from academic_guardrail.providers.openalex import OpenAlexProvider
from academic_guardrail.providers.crossref import CrossrefProvider
from academic_guardrail.core.ref_resolver import (
    ReferenceResolver, add_retraction_evidence, merge_candidate_evidence,
)
from academic_guardrail.core.models import Citation
from academic_guardrail.core.exceptions import ProviderError, RateLimitError

logger = logging.getLogger(__name__)

CHINESE_CORE_JOURNALS = [
    "管理世界", "经济研究", "金融研究", "软件学报", "计算机学报", "中国社会科学",
    "法学研究", "世界经济", "会计研究", "中国工业经济", "数理统计与管理", "情报学报",
    "中国管理科学", "中国人力资源开发", "城市发展研究", "数量经济技术经济研究", "地理学报",
    "经济学(季刊)", "经济学季刊", "经济理论与经济管理", "城市规划", "中国软科学", "学术界", "统计研究", "思想战线"
]


from academic_guardrail.providers.retraction_db import OfflineRetractionDB
from academic_guardrail.core.cache import get_cache, SqliteCache


class ChineseAcademicProvider:
    """Gather metadata; leave final risk decisions to the service decision function."""

    def __init__(
        self,
        email: Optional[str] = None,
        client: Optional[AcademicHttpClient] = None,
        max_concurrency: int = 5,
        cache: Optional[SqliteCache] = None,
    ):
        self.email = email or os.environ.get("ACADEMIC_GUARDRAIL_EMAIL", "academic-guardrail@example.com")
        self.client = client or AcademicHttpClient(email=self.email)
        self.cache = cache or get_cache()
        self.retraction_db = OfflineRetractionDB()
        self.openalex = OpenAlexProvider(email=self.email, client=self.client, cache=self.cache)
        self.crossref = CrossrefProvider(email=self.email, client=self.client, cache=self.cache)
        self.resolver = ReferenceResolver()
        self.max_concurrency = max_concurrency
        self._sem: Optional[asyncio.Semaphore] = None

    async def close(self):
        """Closes the underlying HTTP client session."""
        try:
            if hasattr(self.client, "close"):
                await self.client.close()
        finally:
            self.retraction_db.close()

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
        cache_key = self.cache.make_key("s2_search_v2", query.lower().strip(), str(limit))
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        base = os.environ.get("SEMANTIC_SCHOLAR_API_BASE", "https://api.semanticscholar.org/graph/v1")
        url = (f"{base}/paper/search?query={urllib.parse.quote(query, safe='')}&limit={limit}"
               "&fields=title,authors,year,externalIds,abstract,isRetracted,venue")
        response = await self.client.get_json(url)
        if not response or not isinstance(response.get("data"), list):
            raise ProviderError("Semantic Scholar returned an invalid search response")
        results = []
        for paper in response["data"]:
            results.append(add_retraction_evidence({
                "title": paper.get("title"),
                "doi": ReferenceResolver.normalize_doi((paper.get("externalIds") or {}).get("DOI")),
                "authors": [a["name"] for a in paper.get("authors", []) if a.get("name")],
                "year": paper.get("year"), "venue": paper.get("venue"),
                "abstract": paper.get("abstract") or "",
                "is_retracted": paper.get("isRetracted"),
            }, "Semantic Scholar"))
        # A successful empty search can be cached. Exceptions never reach this line.
        self.cache.set(cache_key, results)
        return results

    @staticmethod
    async def _collect_queries(queries, timeout):
        """Bound the whole collection window and always join canceled children."""
        tasks = {name: asyncio.create_task(query) for name, query in queries}
        try:
            await asyncio.wait(tasks.values(), timeout=timeout)
        finally:
            for task in tasks.values():
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)
        results, failures = {}, {}
        for name, task in tasks.items():
            if task.cancelled():
                failures[name] = "TIMEOUT"
            elif task.exception() is not None:
                exc = task.exception()
                failures[name] = "RATE_LIMITED" if isinstance(exc, RateLimitError) else "PROVIDER_ERROR"
            else:
                results[name] = task.result()
        return results, failures

    def _check_offline(self, candidate):
        """Recheck the selected DOI, including DOIs discovered by title search."""
        result = add_retraction_evidence(candidate)
        doi = ReferenceResolver.normalize_doi(result.get("doi"))
        if not doi:
            return result
        try:
            hit = self.retraction_db.check_doi(doi)
        except ProviderError:
            result["failure_reason"] = "OFFLINE_DB_UNAVAILABLE"
            result["sources"].append({
                "source": "Offline Retraction Watch DB", "kind": "offline_database",
                "identifier": doi, "detail": "Local database lookup failed", "is_retracted": None,
            })
            return result
        if hit:
            result["retraction_info"] = hit.get("reason")
        result["sources"].append({
            "source": "Offline Retraction Watch DB", "kind": "offline_database",
            "identifier": doi, "detail": hit.get("reason") if hit else "No record in configured local database (limited coverage)",
            "is_retracted": bool(hit and hit.get("is_retracted")),
        })
        return add_retraction_evidence(result)

    @staticmethod
    def _matched_result(candidate, source, confidence=1.0):
        result = dict(candidate)
        result.update(matched=True, source=source, confidence=confidence,
                      abstract=candidate.get("abstract") or "",
                      evidence_status="RETRACTED" if candidate.get("is_retracted") else "ARTICLE_MATCHED")
        return result

    @staticmethod
    def _attach_query_outcomes(result, responses, failures, identifier=None):
        """Retain empty queries and failures without inventing retraction findings."""
        result.setdefault("sources", [])
        for name in sorted(set(responses) | set(failures)):
            if name in failures or not responses.get(name):
                result["sources"].append({
                    "source": name, "kind": "query_status", "identifier": identifier,
                    "detail": failures.get(name, "No matching record returned"), "is_retracted": None,
                })
        reasons = [result.get("failure_reason")] + [f"{name}: {reason}" for name, reason in failures.items()]
        result["failure_reason"] = "; ".join(reason for reason in reasons if reason) or None
        return result

    @staticmethod
    def _unresolved(title, doi, failures):
        return {
            "matched": None if failures else False, "doi": doi, "title": title,
            "is_retracted": False, "retraction_status": "NOT_CHECKED", "sources": [],
            "abstract": "", "confidence": 0.0,
            "evidence_status": "PROVIDER_UNAVAILABLE" if failures else "NOT_FOUND",
            "failure_reason": None,
            "source": "Online providers",
        }

    async def _verify_doi(self, title, doi):
        try:
            offline_hit = self.retraction_db.check_doi(doi)
        except ProviderError:
            offline_hit = None  # Online sources can still provide independent evidence.
        if offline_hit:
            return self._matched_result(self._check_offline(offline_hit), "Offline Retraction Watch DB")
        results, failures = await self._collect_queries([
            ("OpenAlex", self.openalex.get_by_doi(doi)),
            ("Crossref", self.crossref.get_by_doi(doi)),
        ], timeout=8.0)
        records = []
        for name, record in results.items():
            if not record:
                continue
            if not isinstance(record, dict) or ReferenceResolver.normalize_doi(record.get("doi")) != doi:
                failures[name] = "IDENTITY_MISMATCH"
                continue
            records.append(add_retraction_evidence(record, name))
        if not records:
            unresolved = self._unresolved(title, doi, failures)
            unresolved = self._check_offline(unresolved)
            return self._attach_query_outcomes(unresolved, results, failures, doi)
        merged = records[0]
        for record in records[1:]:
            merged = merge_candidate_evidence(merged, record)
        result = self._matched_result(self._check_offline(merged), "Crossref/OpenAlex (DOI)")
        return self._attach_query_outcomes(result, results, failures, doi)

    async def _verify_title(self, citation):
        title = citation.title or ""
        core = self._extract_core_title(title)
        query = core if len(core) >= 5 else title
        if len(query) < 3:
            return self._unresolved(title, None, {})
        results, failures = await self._collect_queries([
            ("OpenAlex", self.openalex.search_by_title(query, per_page=5)),
            ("Semantic Scholar", self._search_semantic_scholar_candidates(query, limit=5)),
            ("Crossref", self.crossref.search_by_title(query, rows=5)),
        ], timeout=1.5)
        candidates = []
        for name, records in results.items():
            if not isinstance(records, list):
                failures[name] = "INVALID_RESPONSE"
                continue
            for record in records:
                candidate = add_retraction_evidence(record, name)
                candidate["source"] = name
                candidates.append(candidate)
        best = self.resolver.select_best_candidate(citation, candidates, min_score=0.40)
        if best and best.get("title"):
            best = self._check_offline(best)
            # Supplement only a resolved identity; merge evidence as well as the abstract.
            doi = ReferenceResolver.normalize_doi(best.get("doi"))
            if doi and not best.get("abstract") and not best.get("is_uncertain"):
                extra, extra_failures = await self._collect_queries([
                    ("OpenAlex", self.openalex.get_by_doi(doi))], timeout=5.0)
                record = extra.get("OpenAlex")
                if record and ReferenceResolver.normalize_doi(record.get("doi")) == doi:
                    best = merge_candidate_evidence(best, add_retraction_evidence(record, "OpenAlex"))
                failures.update(extra_failures)
            result = self._matched_result(best, f"{best.get('source', 'Online Search')} (Global Rerank)",
                                          round(best.get("match_score", 0.0), 2))
            return self._attach_query_outcomes(result, results, failures, doi)
        result = self._unresolved(title, None, failures)
        corpus = f"{title} {citation.raw_text or ''}"
        journal = next((j for j in CHINESE_CORE_JOURNALS if j in corpus), None)
        if journal and not failures:
            result.update(matched=None, confidence=0.40,
                          evidence_status="JOURNAL_MATCHED_ARTICLE_UNVERIFIED",
                          source=f"期刊名称启发式规则 ({journal})",
                          message="期刊名称命中不构成文章身份确认，请手工核查原刊。")
        return self._attach_query_outcomes(result, results, failures)

    async def verify_citation(self, title: str, doi: Optional[str] = None,
                              authors: Optional[list] = None, raw_text: Optional[str] = None,
                              year: Optional[int] = None) -> Dict[str, Any]:
        clean_doi = ReferenceResolver.normalize_doi(doi or title)
        citation = Citation(id="cit_verify", raw_text=raw_text or title or "",
                            doi=clean_doi, title=title, authors=authors or [], year=year)
        async with self._get_semaphore():
            if clean_doi:
                return await self._verify_doi(title, clean_doi)
            return await self._verify_title(citation)
