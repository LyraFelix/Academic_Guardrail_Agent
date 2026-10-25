"""Coordinate collection, reference decisions and optional heuristic alignment."""

import asyncio
from typing import Optional

from academic_guardrail.core.exceptions import ProviderError, RateLimitError
from academic_guardrail.core.models import (
    Citation, ContextClaim, DocumentAuditReport, RiskLevel,
    VerificationResult, VerificationStatus,
)
from academic_guardrail.core.parser import DocumentParser
from academic_guardrail.core.ref_resolver import ReferenceResolver
from academic_guardrail.core.ref_store import LocalRefStore
from academic_guardrail.core.reference_decision import decide_reference
from academic_guardrail.providers.chinese_academic import ChineseAcademicProvider
from academic_guardrail.providers.claim_eval import ClaimEvaluator
from academic_guardrail.providers.retraction_db import OfflineRetractionDB


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
        doi = ReferenceResolver.normalize_doi(citation.doi)
        try:
            record = self.retraction_db.check_doi(doi) if doi else None
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
                "detail": f"数据库: {self.retraction_db.db_path}；内置数据只有 3 条历史撤稿示例，不代表完整覆盖。",
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
        evidence = await self._collect_evidence(citation)
        preliminary = decide_reference(citation, evidence)
        # Do not use unrelated local text to resolve online ambiguity or erase a
        # retraction warning. These cases need explicit identity confirmation.
        can_use_local = preliminary.evidence_status not in {
            "AMBIGUOUS", "RETRACTED", "RETRACTION_SUSPECTED",
        }
        if ref_store and can_use_local and (not evidence.get("matched") or not evidence.get("abstract")):
            local = ref_store.find_match(citation)
            if local:
                evidence = {
                    **evidence, "matched": True, "title": local["title"],
                    "doi": evidence.get("doi") if evidence.get("matched") else None,
                    "abstract": local.get("abstract") or local.get("fulltext") or "",
                    "confidence": local["match_score"], "evidence_status": "LOCAL_MATCHED",
                    "resolution_metadata": local.get("resolution_metadata"),
                    "sources": [*(evidence.get("sources") or []), {
                        "source": local["filename"], "kind": "local_file",
                        "identifier": local["filepath"], "detail": "从用户提供的文件提取标题和文本",
                    }],
                }
        return decide_reference(citation, evidence)

    async def verify_single_item(self, cit: Citation, claim: ContextClaim,
                                 ref_store: Optional[LocalRefStore] = None) -> VerificationResult:
        result = await self.verify_reference(cit, ref_store)
        result.claim = claim
        if result.status != VerificationStatus.VALID or not result.evidence_text or not claim.claim_sentence.strip():
            return result

        score, reason, sentence, state, engine = self.evaluator.evaluate_alignment(
            claim.claim_sentence, result.evidence_text)
        result.verification_scope = "HEURISTIC_ALIGNMENT"
        result.claim_alignment_score = score
        result.alignment_state = state
        result.alignment_engine = engine
        result.semantic_mode = ("FULL" if engine == "vector_embedding" else
                                "CORE_FALLBACK" if self.evaluator.semantic_matcher._model_load_failed else "CORE")
        result.evidence_text = sentence or result.evidence_text
        result.evidence_granularity = "SENTENCE" if sentence else "FULL_ABSTRACT"
        descriptions = {
            "SUPPORTED": "文本具有较高相似度，仍需人工确认其是否支持断言。",
            "PARTIAL": "文本部分相似，请检查是否缺少条件或限定范围。",
            "NEUTRAL": "未找到直接对应的文本，请人工检查全文。",
            "CONTRADICTED": "检测到可能的否定或方向冲突，请人工检查语境。",
        }
        if state == "CONTRADICTED":
            result.status, result.risk_level = VerificationStatus.CLAIM_MISMATCH, RiskLevel.WARNING
        elif state in {"NEUTRAL", "PARTIAL"}:
            result.status, result.risk_level = VerificationStatus.CLAIM_MISMATCH, RiskLevel.NOTICE
        elif state != "SUPPORTED":
            result.status, result.risk_level = VerificationStatus.UNVERIFIED, RiskLevel.WARNING
        result.message += " 启发式文本比对：" + descriptions.get(state, "对齐状态未知，请人工确认。")
        result.message += f" 匹配分数 {score:.2f}。{reason} 此结果不构成事实蕴含或学术诚信结论。"
        return result

    async def audit_document(self, file_path: str,
                             refs_dir: Optional[str] = None) -> DocumentAuditReport:
        pairs = self.parser.parse_document(file_path)
        ref_store = LocalRefStore(refs_dir) if refs_dir else None
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def bounded_verify(citation, claim):
            async with semaphore:
                return await self.verify_single_item(citation, claim, ref_store)

        results = await asyncio.gather(*(bounded_verify(cit, claim) for cit, claim in pairs))
        return DocumentAuditReport(
            document_path=file_path, offline=self.offline, total_citations=len(results),
            passed_count=sum(r.risk_level == RiskLevel.PASS for r in results),
            notice_count=sum(r.risk_level == RiskLevel.NOTICE for r in results),
            warning_count=sum(r.risk_level == RiskLevel.WARNING for r in results),
            danger_count=sum(r.risk_level == RiskLevel.DANGER for r in results),
            results=results,
        )
