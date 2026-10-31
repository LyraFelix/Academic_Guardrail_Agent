"""Coordinate collection, reference decisions and optional heuristic alignment."""

import asyncio
from dataclasses import dataclass
from typing import Optional

from academic_guardrail.core.exceptions import ProviderError, RateLimitError
from academic_guardrail.core.models import (
    Citation, ContextClaim, DocumentAuditReport, RiskLevel, EvidencePassage, EvidenceStatus,
    VerificationResult, VerificationStatus,
)
from academic_guardrail.core.parser import DocumentParser
from academic_guardrail.core.ref_resolver import ReferenceResolver
from academic_guardrail.core.ref_store import LocalRefStore
from academic_guardrail.core.reference_decision import decide_reference
from academic_guardrail.providers.chinese_academic import ChineseAcademicProvider
from academic_guardrail.providers.claim_eval import ClaimEvaluator
from academic_guardrail.providers.retraction_db import OfflineRetractionDB


@dataclass
class PreparedReference:
    """Shared identity decision and source text; each occurrence gets its own result."""

    result: VerificationResult
    passages: list[EvidencePassage]


class AuditService:
    """One decision path for every public entry point.

    Offline mode never constructs an HTTP provider or initializes an embedding
    model. A local match establishes only the identity of the supplied file.
    """

    def __init__(self, max_concurrency: int = 5, request_timeout: float = 35.0,
                 offline: bool = False, email: Optional[str] = None):
        if max_concurrency < 1 or request_timeout <= 0:
            raise ValueError("Concurrency and timeout must be positive")
        self.max_concurrency = max_concurrency
        self.request_timeout = request_timeout
        self.offline = offline
        self.parser = DocumentParser()
        self.provider = None if offline else ChineseAcademicProvider(
            max_concurrency=max_concurrency, email=email)
        self.retraction_db = OfflineRetractionDB() if offline else None
        self.evaluator = ClaimEvaluator(use_embeddings=not offline)

    async def close(self):
        if self.provider is not None:
            await self.provider.close()
        if self.retraction_db is not None:
            self.retraction_db.close()

    def _offline_evidence(self, citation: Citation) -> dict:
        """Consult the local retraction DB, including after an online local fallback."""
        doi = ReferenceResolver.normalize_doi(citation.doi)
        database = self.retraction_db if self.offline else self.provider.retraction_db
        try:
            record = database.check_doi(doi) if doi else None
        except ProviderError:
            return {
                "matched": False, "retraction_status": "NOT_CHECKED",
                "failure_reason": "OFFLINE_DB_UNAVAILABLE", "evidence_status": "PROVIDER_UNAVAILABLE",
                "sources": [{"source": "Local retraction database", "kind": "offline_database",
                             "identifier": doi, "detail": "本地数据库读取失败，未完成检查", "is_retracted": None}],
            }
        sources = []
        if doi:
            sources.append({
                "source": "Local retraction database", "kind": "offline_database",
                "identifier": doi, "is_retracted": bool(record),
                "detail": f"数据库: {database.db_path}；内置数据只有 3 条历史撤稿示例，不代表完整覆盖。",
            })
        return {
            **(record or {}), "matched": bool(record), "sources": sources,
            "confidence": 1.0 if record else 0.0,
            "retraction_status": "CONFIRMED" if record else ("NO_RECORD" if doi else "NOT_CHECKED"),
            "retraction_info": record.get("reason") if record else None,
            "evidence_status": "RETRACTED" if record else "OFFLINE_NO_MATCH",
        }

    async def _collect_evidence(self, citation: Citation) -> dict:
        if self.offline:
            return self._offline_evidence(citation)
        try:
            return await asyncio.wait_for(
                self.provider.verify_citation(
                    title=citation.title or citation.raw_text, doi=citation.doi,
                    raw_text=citation.raw_text, authors=citation.authors, year=citation.year),
                timeout=self.request_timeout,
            )
        except asyncio.TimeoutError:
            reason = "TIMEOUT"
        except RateLimitError:
            reason = "RATE_LIMITED"
        except ProviderError:
            reason = "PROVIDER_ERROR"
        # Keep failures as observations so a local fallback can still run.
        return {"matched": False, "evidence_status": "PROVIDER_UNAVAILABLE",
                "failure_reason": reason, "retraction_status": "NOT_CHECKED"}

    async def verify_reference(self, citation: Citation,
                               ref_store: Optional[LocalRefStore] = None) -> VerificationResult:
        """Collect reference evidence and apply the shared precedence rules."""
        return (await self._prepare_reference(citation, ref_store)).result

    async def _prepare_reference(self, citation: Citation,
                                 ref_store: Optional[LocalRefStore] = None) -> PreparedReference:
        if citation.parse_status != "PARSED" or not (citation.title or citation.doi):
            result = decide_reference(citation, {"is_uncertain": citation.parse_status == "AMBIGUOUS"})
            result.evidence_status = EvidenceStatus.PARSE_INCOMPLETE
            result.message = "引用条目缺失、重复或没有可用标题/DOI；请先修正解析结果，未执行数据源查询。"
            return PreparedReference(result, [])
        evidence = await self._collect_evidence(citation)
        preliminary = decide_reference(citation, evidence)
        can_use_local = preliminary.evidence_status not in {
            "AMBIGUOUS", "RETRACTED", "RETRACTION_SUSPECTED",
        }
        passages = []
        if preliminary.status == VerificationStatus.VALID and preliminary.evidence_text:
            passages.append(EvidencePassage(text=preliminary.evidence_text, source_kind="ONLINE_ABSTRACT"))
        local_ambiguous, local = None, None
        if ref_store and can_use_local:
            # Online resolution may discover a DOI absent from the manuscript.
            # Use that resolved identity, not the original incomplete title query.
            identity = citation.model_copy(update={
                "title": preliminary.verified_title or citation.title,
                "doi": preliminary.verified_doi or citation.doi})
            local = ref_store.select_candidate(identity)
            if local and local.get("is_uncertain"):
                local_ambiguous = local.get("ambiguous_candidates") or []
                if preliminary.status != VerificationStatus.VALID:
                    evidence.update(is_uncertain=True, ambiguous_candidates=local_ambiguous)
            elif local:
                was_matched = preliminary.status == VerificationStatus.VALID
                if local.get("doi") and not identity.doi:
                    # Title-only matches can reveal a DOI. Recheck its retraction
                    # status before making any text available to the evaluator.
                    check = self._offline_evidence(identity.model_copy(update={"doi": local["doi"]}))
                    evidence.update({key: check[key] for key in ("retraction_status", "retraction_info") if key in check})
                    evidence["sources"] = [*(evidence.get("sources") or []), *(check.get("sources") or [])]
                    failures = [evidence.get("failure_reason"), check.get("failure_reason")]
                    evidence["failure_reason"] = " | ".join(value for value in failures if value) or None
                evidence.update(
                    matched=True, title=preliminary.verified_title or local["title"],
                    doi=preliminary.verified_doi or local.get("doi") or citation.doi,
                    abstract=preliminary.abstract_tldr or local.get("abstract") or None,
                    confidence=evidence.get("confidence") if was_matched else local["match_score"],
                    evidence_status=preliminary.evidence_status if was_matched else "LOCAL_MATCHED",
                    resolution_metadata=evidence.get("resolution_metadata") if was_matched else local.get("resolution_metadata"),
                    sources=[*(evidence.get("sources") or []), {
                        "source": local["filename"], "kind": "local_file",
                        "identifier": local["filepath"], "detail": "本地文件身份匹配；检索范围为参考文献列表之前的全文段落。",
                    }])
                passages = [EvidencePassage.model_validate(p) for p in local.get("passages", [])] or passages
        result = decide_reference(citation, evidence)
        if local_ambiguous is not None:
            result.ambiguous_candidates = local_ambiguous
            result.retrieval_status = "AMBIGUOUS"
            result.message += " 本地参考文件存在歧义，未使用这些文件的文本。"
        if result.status != VerificationStatus.VALID:
            passages = []
        if result.evidence_text:
            if preliminary.abstract_tldr:
                result.text_source = "ONLINE_ABSTRACT"
            elif local and not local.get("is_uncertain") and local.get("abstract"):
                result.text_source = "LOCAL_ABSTRACT"
                if local.get("abstract_location"):
                    from academic_guardrail.core.models import SourceLocation
                    result.evidence_location = SourceLocation.model_validate(local["abstract_location"])
        return PreparedReference(result, passages)

    async def verify_single_item(self, cit: Citation, claim: Optional[ContextClaim],
                                 ref_store: Optional[LocalRefStore] = None) -> VerificationResult:
        prepared = await self._prepare_reference(cit, ref_store)
        return self._evaluate_occurrence(prepared, claim)

    def _evaluate_occurrence(self, prepared: PreparedReference,
                             claim: Optional[ContextClaim]) -> VerificationResult:
        result = prepared.result.model_copy(deep=True)
        result.claim = claim
        if not claim or not claim.claim_sentence.strip() or result.status != VerificationStatus.VALID:
            return result
        result.verification_scope = "TEXT_RETRIEVAL"
        result.evidence_text = None
        result.evidence_location = None
        result.evidence_granularity = None
        result.text_source = None
        if not prepared.passages:
            if result.retrieval_status != "AMBIGUOUS":
                result.retrieval_status = "NO_TEXT"
            result.status, result.risk_level = VerificationStatus.UNVERIFIED, RiskLevel.NOTICE
            result.alignment_state = "INSUFFICIENT_EVIDENCE"
            result.message += " 文献元数据已匹配，但没有可用文本核验这处正文引用。"
            result.evidence_text = None
            return result
        assessment = self.evaluator.assess_passages(claim.claim_sentence, prepared.passages)
        result.alignment_state = assessment.state
        result.alignment_engine = assessment.alignment_engine
        result.claim_alignment_score = assessment.similarity_score
        result.semantic_findings = assessment.findings
        if assessment.state == "INSUFFICIENT_EVIDENCE":
            result.retrieval_status = "NO_RELEVANT_PASSAGE"
            result.status, result.risk_level = VerificationStatus.UNVERIFIED, RiskLevel.NOTICE
            result.message += " 未找到主体和指标对应的可比文本；这不表示断言为假。"
            return result
        result.verification_scope = "RULE_BASED_REVIEW"
        result.retrieval_status = "AVAILABLE"
        result.text_source = assessment.text_source
        result.semantic_mode = ("FULL" if assessment.alignment_engine == "vector_embedding" else
                                "CORE_FALLBACK" if self.evaluator.semantic_matcher._model_load_failed else "CORE")
        result.evidence_text = assessment.evidence_text
        result.evidence_location = assessment.evidence_location
        result.evidence_granularity = "CLAUSE"
        if assessment.state == "POTENTIAL_CONFLICT":
            result.status, result.risk_level = VerificationStatus.CLAIM_MISMATCH, RiskLevel.WARNING
        elif assessment.state == "REVIEW_REQUIRED":
            result.status, result.risk_level = VerificationStatus.CLAIM_MISMATCH, RiskLevel.NOTICE
        else:
            # Metadata can remain VALID; a claim check never receives PASS.
            result.risk_level = RiskLevel.NOTICE
        result.message += " 规则文字检查：" + assessment.message
        result.message += f" 检索相似度 {assessment.similarity_score:.2f}（非真实性概率）。"
        return result

    async def audit_document(self, file_path: str,
                             refs_dir: Optional[str] = None) -> DocumentAuditReport:
        parsed = self.parser.parse(file_path)
        ref_store = LocalRefStore(refs_dir, excluded_paths=[file_path]) if refs_dir else None
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def bounded_prepare(citation):
            async with semaphore:
                return await self._prepare_reference(citation, ref_store)

        prepared = await asyncio.gather(*(bounded_prepare(cit) for cit in parsed.citations))
        by_id = {item.result.citation.id: item for item in prepared}
        results = [self._evaluate_occurrence(by_id[claim.citation_id], claim) for claim in parsed.occurrences]
        cited_ids = {claim.citation_id for claim in parsed.occurrences}
        results.extend(item.result for item in prepared if item.result.citation.id not in cited_ids)
        return DocumentAuditReport(
            document_path=file_path, offline=self.offline, total_citations=len(results),
            total_references=sum(cit.parse_status != "MISSING" for cit in parsed.citations),
            total_occurrences=len(parsed.occurrences),
            parse_diagnostics=[*parsed.diagnostics, *(ref_store.diagnostics if ref_store else [])],
            passed_count=sum(r.risk_level == RiskLevel.PASS for r in results),
            notice_count=sum(r.risk_level == RiskLevel.NOTICE for r in results),
            warning_count=sum(r.risk_level == RiskLevel.WARNING for r in results),
            danger_count=sum(r.risk_level == RiskLevel.DANGER for r in results),
            results=results,
        )
