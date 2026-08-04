"""Model Context Protocol (MCP) Server for Academic Guardrail Agent."""

import asyncio
from mcp.server.fastmcp import FastMCP

from academic_guardrail.core.models import (
    Citation, ContextClaim, VerificationResult, VerificationStatus, RiskLevel, DocumentAuditReport
)
from academic_guardrail.core.parser import DocumentParser
from academic_guardrail.providers.chinese_academic import ChineseAcademicProvider
from academic_guardrail.providers.claim_eval import ClaimEvaluator

mcp = FastMCP("Academic Guardrail Agent")
provider = ChineseAcademicProvider()
evaluator = ClaimEvaluator()
parser = DocumentParser()


@mcp.tool()
async def verify_single_citation(citation_str_or_doi: str) -> str:
    """验证单条文献引用的真实性、DOI 匹配及撤稿状态。"""
    is_doi = citation_str_or_doi.startswith("10.") or "doi.org" in citation_str_or_doi
    doi = citation_str_or_doi if is_doi else None
    title = citation_str_or_doi if not is_doi else ""

    res = await provider.verify_citation(title=title, doi=doi)

    if res.get("is_retracted"):
        return f"🔴 [DANGER/撤稿警示] 该论文已被撤稿或发出了学术质疑 (DOI: {res.get('doi')})"
    elif res.get("matched"):
        return f"🟢 [PASS/验证通过] 匹配论文《{res.get('title')}》 (DOI: {res.get('doi')})"
    else:
        return f"🟡 [WARNING/未查证] 无法在数据库中核实该文献，请检查拼写或格式 (输入: {citation_str_or_doi})"


@mcp.tool()
async def check_paper_retraction(doi: str) -> str:
    """专门查询指定 DOI 论文是否存在撤稿记录。"""
    res = await provider.verify_citation(title="", doi=doi)
    if res.get("is_retracted"):
        return f"🔴 [RETRACTED] 论文 {doi} 已被撤稿！"
    elif res.get("matched"):
        return f"🟢 [OK] 论文 {doi} 状态正常，未发现撤稿记录。"
    else:
        return f"🟡 [UNKNOWN] 未能检索到 DOI {doi} 的纪录。"


@mcp.tool()
async def audit_document_claims(file_path: str) -> str:
    """全面审计论文原稿（.pdf, .docx, .md, .tex），检查引用真实性与断言一致性。"""
    try:
        pairs = parser.parse_document(file_path)
    except Exception as e:
        return f"❌ 无法解析文档: {str(e)}"

    if not pairs:
        return "ℹ️ 未在文档中识别出任何文献引用标记或 GB/T 7714 格式。"

    results = []
    passed = 0
    warning = 0
    danger = 0

    for cit, claim in pairs:
        verify_res = await provider.verify_citation(title=cit.title or cit.raw_text, doi=cit.doi)
        
        if verify_res.get("is_retracted"):
            status = VerificationStatus.RETRACTED
            risk = RiskLevel.DANGER
            msg = "🔴 论文存在撤稿记录，存在严重学术合规风险！"
            danger += 1
        elif verify_res.get("matched"):
            score, reason = evaluator.evaluate_alignment(claim.claim_sentence, verify_res.get("abstract", ""))
            if score < 0.40:
                status = VerificationStatus.CLAIM_MISMATCH
                risk = RiskLevel.NOTICE
                msg = f"🔵 断言一致性较弱 ({score})。{reason}"
                passed += 1
            else:
                status = VerificationStatus.VALID
                risk = RiskLevel.PASS
                msg = f"🟢 匹配成功，文献正常 ({verify_res.get('source')})。"
                passed += 1
        else:
            status = VerificationStatus.UNVERIFIED
            risk = RiskLevel.WARNING
            msg = "🟡 数据库未查证到该文献，请确认格式或手写准确性。"
            warning += 1

        v_item = VerificationResult(
            citation=cit,
            claim=claim,
            status=status,
            risk_level=risk,
            verified_title=verify_res.get("title"),
            verified_doi=verify_res.get("doi"),
            abstract_tldr=verify_res.get("abstract"),
            message=msg
        )
        results.append(v_item)

    report = DocumentAuditReport(
        document_path=file_path,
        total_citations=len(pairs),
        passed_count=passed,
        warning_count=warning,
        danger_count=danger,
        results=results
    )

    summary = f"🛡️ **文档审计完成**: 总引用 {report.total_citations} 项 | 🟢 通过 {report.passed_count} | 🟡 警告 {report.warning_count} | 🔴 高危 {report.danger_count}\n"
    for r in report.results:
        summary += f"- [{r.risk_level.value}] {r.citation.raw_text[:40]}... -> {r.message}\n"

    return summary


def main():
    mcp.run()


if __name__ == "__main__":
    main()
