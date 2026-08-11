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
from academic_guardrail.core.config import GuardrailConfig


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
            alignment_state = None
            msg = f"🔴 撤稿高危：文献《{verify_res.get('title', '')}》存在撤稿或预警记录 (Retracted Paper)，存在严重学术诚信风险！"
            return VerificationResult(
                citation=cit,
                claim=claim,
                status=status,
                risk_level=risk,
                verified_title=verify_res.get("title"),
                verified_doi=verify_res.get("doi"),
                abstract_tldr=verify_res.get("abstract"),
                reference_confidence=ref_confidence,
                alignment_state=alignment_state,
                message=msg
            )
        else:
            abstract = verify_res.get("abstract", "")
            source_name = verify_res.get("source", "权威数据库")
            is_matched = verify_res.get("matched", False)
            is_uncertain = verify_res.get("is_uncertain", False) or verify_res.get("match_confidence") == "UNCERTAIN"
            ref_confidence = verify_res.get("confidence", 0.0) if is_matched else 0.0

            if is_uncertain:
                is_matched = False

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
            alignment_state = None
            alignment_engine = None
            amb_list = verify_res.get("ambiguous_candidates")
            margin_val = verify_res.get("match_margin", 0.0)

            evidence_status = verify_res.get("evidence_status")

            if is_uncertain:
                status = VerificationStatus.UNVERIFIED
                risk = RiskLevel.WARNING
                ref_confidence = verify_res.get("confidence", 0.0)
                alignment_state = "UNCERTAIN"
                compare_lines = []
                if amb_list:
                    for idx, c in enumerate(amb_list, 1):
                        doi_info = f" (DOI: {c['doi']})" if c.get('doi') else ""
                        compare_lines.append(f"  [{idx}] 《{c.get('title', '')}》{doi_info} [匹配得分: {c.get('score', 0.0):.2f}, 来源: {c.get('source', '')}]")
                details_str = "\n".join(compare_lines) if compare_lines else "  暂无双候选数据"
                msg = (
                    f"🟡 存在匹配歧义：检索到多篇极其相似的相关候选文献（首选得分 {ref_confidence:.2f}，差值 {margin_val:.2f} < 5%）：\n"
                    f"{details_str}\n"
                    f"系统无法确定唯一精准目标，请在手稿中显式标识 DOI 或补全文献标题以消除歧义。"
                )
            elif evidence_status == "JOURNAL_MATCHED_ARTICLE_UNVERIFIED":
                status = VerificationStatus.UNVERIFIED
                risk = RiskLevel.NOTICE
                ref_confidence = verify_res.get("confidence", 0.40)
                alignment_state = "UNVERIFIED"
                msg = verify_res.get("message", "🔵 期刊在录待查：检测到文章引自中文核心期刊，具体文章尚未核实。")
            elif not is_matched:
                status = VerificationStatus.UNVERIFIED
                risk = RiskLevel.WARNING
                ref_confidence = 0.0
                alignment_state = "UNVERIFIED"
                msg = "🟡 数据库未核实该文献，请检查拼写或手工确认。"
            elif not target_abstract:
                status = VerificationStatus.VALID
                risk = RiskLevel.PASS
                alignment_state = "NEUTRAL"
                msg = f"🟢 文献存在于{source_name}。因数据库及本地库未收录摘要原文，已完成元数据校验。"
            else:
                score, reason, best_sent, alignment_state, alignment_engine = self.evaluator.evaluate_alignment(claim.claim_sentence, target_abstract)
                context_str = f" [最匹配的原句: \"{best_sent[:120]}...\"]" if best_sent else ""

                if alignment_state == "CONTRADICTED":
                    status = VerificationStatus.CLAIM_MISMATCH
                    risk = RiskLevel.DANGER
                    msg = f"🔴 显式极性矛盾：文献核心结论与正文断言存在语法否定或相反逻辑 ({score:.2f})。{reason}{context_str}"
                elif alignment_state == "NEUTRAL":
                    status = VerificationStatus.CLAIM_MISMATCH
                    risk = RiskLevel.NOTICE
                    msg = f"🔵 缺乏直接依据：文献摘要未直接提供支持该特定结论的因果证据 ({score:.2f})。{reason}{context_str}"
                elif alignment_state == "PARTIAL":
                    status = VerificationStatus.CLAIM_MISMATCH
                    risk = RiskLevel.NOTICE
                    msg = f"🟡 部分对齐：正文断言与文献摘要呈现中度相关（仅背景或部分吻合）({score:.2f})。{reason}{context_str}"
                else: # SUPPORTED
                    status = VerificationStatus.VALID
                    risk = RiskLevel.PASS
                    msg = f"🟢 高度一致：正文断言与文献摘要呈现高相关对齐 ({score:.2f})。{reason}{context_str}"

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
            alignment_state=alignment_state,
            alignment_engine=alignment_engine,
            resolution_metadata=verify_res.get("resolution_metadata"),
            ambiguous_candidates=verify_res.get("ambiguous_candidates") if is_uncertain else None,
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
                notice_count=0,
                warning_count=0,
                danger_count=0,
                results=[]
            )

        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def _bounded_verify(cit, claim):
            async with semaphore:
                return await self.verify_single_item(cit, claim, ref_store)

        results = await asyncio.gather(*[_bounded_verify(cit, claim) for cit, claim in pairs])

        passed = sum(1 for r in results if r.risk_level == RiskLevel.PASS)
        notice = sum(1 for r in results if r.risk_level == RiskLevel.NOTICE)
        warning = sum(1 for r in results if r.risk_level == RiskLevel.WARNING)
        danger = sum(1 for r in results if r.risk_level == RiskLevel.DANGER)

        return DocumentAuditReport(
            document_path=file_path,
            total_citations=len(pairs),
            passed_count=passed,
            notice_count=notice,
            warning_count=warning,
            danger_count=danger,
            results=results
        )
