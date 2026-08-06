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

    def __init__(self, max_concurrency: int = 5, request_timeout: float = 25.0):
        self.max_concurrency = max_concurrency
        self.request_timeout = request_timeout
        self.parser = DocumentParser()
        self.provider = ChineseAcademicProvider()
        self.evaluator = ClaimEvaluator()

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
                message="🟡 请求超时：数据库查证已超过 15 秒限制"
            )
        except RateLimitError as e:
            return VerificationResult(
                citation=cit,
                claim=claim,
                status=VerificationStatus.UNVERIFIED,
                risk_level=RiskLevel.WARNING,
                message=f"🟡 触发 API 速率限制: {e}"
            )
        except ProviderError as e:
            return VerificationResult(
                citation=cit,
                claim=claim,
                status=VerificationStatus.UNVERIFIED,
                risk_level=RiskLevel.WARNING,
                message=f"🟡 线上数据库检索失败: {e}"
            )

        if verify_res.get("is_retracted"):
            status = VerificationStatus.RETRACTED
            risk = RiskLevel.DANGER
            msg = "🔴 论文存在撤稿记录，存在严重学术合规风险！"
        else:
            abstract = verify_res.get("abstract", "")
            source_name = verify_res.get("source", "权威数据库")
            is_matched = verify_res.get("matched", False)

            # Fallback to local reference file if unverified or online abstract is missing
            local_abstract = None
            if (not is_matched or not abstract) and ref_store:
                match_res = ref_store.find_abstract_for_citation(cit.title or "", cit.raw_text)
                if match_res:
                    local_abstract, ref_filename = match_res
                    source_name = f"本地参考文献 ({ref_filename})"
                    is_matched = True

            target_abstract = abstract or local_abstract

            if not is_matched:
                status = VerificationStatus.UNVERIFIED
                risk = RiskLevel.WARNING
                msg = "🟡 数据库未核实该文献，请检查拼写或手工确认。"
            elif not target_abstract:
                status = VerificationStatus.VALID
                risk = RiskLevel.PASS
                msg = f"🟢 文献存在于{source_name}。因数据库及本地库未收录摘要原文，已完成元数据校验并跳过断言比对。"
            else:
                score, reason, best_sent = self.evaluator.evaluate_alignment(claim.claim_sentence, target_abstract)
                context_str = f" [最匹配的原句: \"{best_sent[:120]}...\"]" if best_sent else ""
                if score < 0.20:
                    status = VerificationStatus.CLAIM_MISMATCH
                    risk = RiskLevel.NOTICE
                    msg = f"🔵 正文断言与{source_name}摘要语义匹配度较弱 ({score:.2f})。{reason}{context_str}"
                else:
                    status = VerificationStatus.VALID
                    risk = RiskLevel.PASS
                    msg = f"🟢 正文断言与{source_name}摘要核心观点高度吻合 ({score:.2f})。{reason}{context_str}"

        return VerificationResult(
            citation=cit,
            claim=claim,
            status=status,
            risk_level=risk,
            verified_title=verify_res.get("title"),
            verified_doi=verify_res.get("doi"),
            abstract_tldr=verify_res.get("abstract"),
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
