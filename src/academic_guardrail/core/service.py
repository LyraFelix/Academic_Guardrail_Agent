"""Audit Service Layer orchestrating document parsing, citation lookup, claim evaluation, and report generation."""

import asyncio
from typing import Optional, List, Tuple
from academic_guardrail.core.parser import DocumentParser
from academic_guardrail.core.ref_store import LocalRefStore
from academic_guardrail.core.models import (
    Citation, ContextClaim, VerificationResult, VerificationStatus, RiskLevel, DocumentAuditReport
)
from academic_guardrail.core.exceptions import (
    AcademicGuardrailError, ParserError, ProviderError, RateLimitError, VerificationError
)
from academic_guardrail.providers.chinese_academic import ChineseAcademicProvider
from academic_guardrail.providers.claim_eval import ClaimEvaluator


class AuditService:
    """Core Service Layer for Academic Guardrail Agent."""

    def __init__(self, max_concurrency: int = 5, request_timeout: float = 35.0):
        self.max_concurrency = max_concurrency
        self.request_timeout = request_timeout
        self.parser = DocumentParser()
        self.provider = ChineseAcademicProvider(max_concurrency=max_concurrency)
        self.evaluator = ClaimEvaluator()

    async def close(self):
        """Closes provider HTTP client session pools."""
        if hasattr(self.provider, "client") and self.provider.client:
            await self.provider.client.close()

    async def verify_single_item(
        self,
        cit: Citation,
        claim: ContextClaim,
        ref_store: Optional[LocalRefStore] = None
    ) -> VerificationResult:
        """Verifies a single citation against online databases or local ref store."""
        try:
            verify_res = await asyncio.wait_for(
                self.provider.verify_citation(title=cit.title or cit.raw_text, doi=cit.doi, raw_text=cit.raw_text),
                timeout=self.request_timeout
            )
        except asyncio.TimeoutError:
            return VerificationResult(
                citation=cit,
                claim=claim,
                status=VerificationStatus.UNVERIFIED,
                risk_level=RiskLevel.WARNING,
                reference_confidence=0.0,
                message="🟡 请求超时：数据库查证已超过限制"
            )
        except RateLimitError as e:
            return VerificationResult(
                citation=cit,
                claim=claim,
                status=VerificationStatus.UNVERIFIED,
                risk_level=RiskLevel.WARNING,
                reference_confidence=0.0,
                message=f"🟡 触发 API 速率限制: {e}"
            )
        except ProviderError as e:
            return VerificationResult(
                citation=cit,
                claim=claim,
                status=VerificationStatus.UNVERIFIED,
                risk_level=RiskLevel.WARNING,
                reference_confidence=0.0,
                message=f"🟡 线上数据库检索失败: {e}"
            )

        if verify_res.get("is_retracted"):
            status = VerificationStatus.RETRACTED
            risk = RiskLevel.DANGER
            ref_confidence = verify_res.get("confidence", 1.0)
            nli_state = "CONTRADICTED"
            msg = "🔴 论文存在撤稿记录，存在严重学术合规风险！"
        else:
            abstract = verify_res.get("abstract", "")
            source_name = verify_res.get("source", "权威数据库")
            is_matched = verify_res.get("matched", False)
            ref_confidence = verify_res.get("confidence", 0.0) if is_matched else 0.0

            # Fallback to local reference file if unverified or online abstract is missing
            local_abstract = None
            if (not is_matched or not abstract) and ref_store:
                match_res = ref_store.find_abstract_for_citation(cit.title or "", cit.raw_text)
                if match_res:
                    local_abstract, ref_filename, local_conf = match_res
                    source_name = f"本地参考文献 ({ref_filename})"
                    is_matched = True
                    ref_confidence = local_conf

            target_abstract = abstract or local_abstract
            score = None

            best_sent = ""
            if not is_matched:
                status = VerificationStatus.UNVERIFIED
                risk = RiskLevel.WARNING
                ref_confidence = 0.0
                nli_state = "UNVERIFIED"
                msg = "🟡 数据库未核实该文献，请检查拼写或手工确认。"
            elif not target_abstract:
                status = VerificationStatus.VALID
                risk = RiskLevel.PASS
                nli_state = "NEUTRAL"
                msg = f"🟢 文献存在于{source_name}。因数据库及本地库未收录摘要原文，已完成元数据校验。"
            else:
                score, reason, best_sent = self.evaluator.evaluate_alignment(claim.claim_sentence, target_abstract)
                context_str = f" [最匹配的原句: \"{best_sent[:120]}...\"]" if best_sent else ""
                if score < 0.35:
                    status = VerificationStatus.CLAIM_MISMATCH
                    risk = RiskLevel.NOTICE
                    nli_state = "CONTRADICTED"
                    msg = f"🔵 正文断言与{source_name}摘要匹配度较弱 ({score:.2f})。{reason}{context_str}"
                else:
                    status = VerificationStatus.VALID
                    risk = RiskLevel.PASS
                    nli_state = "ENTAILED"
                    msg = f"🟢 正文断言与{source_name}摘要核心观点高度吻合 ({score:.2f})。{reason}{context_str}"

        return VerificationResult(
            citation=cit,
            claim=claim,
            status=status,
            risk_level=risk,
            verified_title=verify_res.get("title"),
            verified_doi=verify_res.get("doi"),
            abstract_tldr=best_sent or target_abstract or verify_res.get("abstract"),
            reference_confidence=ref_confidence,
            claim_alignment_score=score,
            nli_state=nli_state,
            message=msg
        )

    async def audit_document(
        self,
        file_path: str,
        refs_dir: Optional[str] = None
    ) -> DocumentAuditReport:
        """Parses and audits a complete document file asynchronously with concurrency control."""
        pairs = self.parser.parse_document(file_path)
        ref_store = LocalRefStore(refs_dir) if refs_dir else None

        if not pairs:
            return DocumentAuditReport(
                document_path=file_path,
                total_citations=0,
                passed_count=0,
                warning_count=0,
                danger_count=0,
                results=[]
            )

        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def _bounded_verify(cit, claim):
            async with semaphore:
                return await self.verify_single_item(cit, claim, ref_store)

        results = await asyncio.gather(*[_bounded_verify(cit, claim) for cit, claim in pairs])

        passed = sum(1 for r in results if r.risk_level in [RiskLevel.PASS, RiskLevel.NOTICE])
        warning = sum(1 for r in results if r.risk_level == RiskLevel.WARNING)
        danger = sum(1 for r in results if r.risk_level == RiskLevel.DANGER)

        return DocumentAuditReport(
            document_path=file_path,
            total_citations=len(pairs),
            passed_count=passed,
            warning_count=warning,
            danger_count=danger,
            results=results
        )
