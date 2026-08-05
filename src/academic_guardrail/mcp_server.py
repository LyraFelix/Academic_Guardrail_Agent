"""Model Context Protocol (MCP) Server for Academic Guardrail Agent."""

import asyncio
from mcp.server.fastmcp import FastMCP

from academic_guardrail.core.models import (
    Citation, ContextClaim, VerificationResult, VerificationStatus, RiskLevel, DocumentAuditReport
)
from academic_guardrail.core.parser import DocumentParser
from academic_guardrail.providers.chinese_academic import ChineseAcademicProvider
from academic_guardrail.providers.claim_eval import ClaimEvaluator

from academic_guardrail.core.service import AuditService

mcp = FastMCP("Academic Guardrail Agent")
service = AuditService()
provider = service.provider


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
        report = await service.audit_document(file_path)
    except Exception as e:
        return f"❌ 无法解析文档: {str(e)}"

    if report.total_citations == 0:
        return "ℹ️ 未在文档中识别出任何文献引用标记或 GB/T 7714 格式。"

    output_lines = [
        f"📊 学术引用与断言审计总结报告: {report.document_path}",
        f"总引用数: {report.total_citations} | 🟢 正常: {report.passed_count} | 🟡 警告: {report.warning_count} | 🔴 撤稿高危: {report.danger_count}\n"
    ]

    for item in report.results:
        output_lines.append(f"• [{item.citation.id}] {item.citation.raw_text[:50]}... => {item.message}")

    return "\n".join(output_lines)

    summary = f"🛡️ **文档审计完成**: 总引用 {report.total_citations} 项 | 🟢 通过 {report.passed_count} | 🟡 警告 {report.warning_count} | 🔴 高危 {report.danger_count}\n"
    for r in report.results:
        summary += f"- [{r.risk_level.value}] {r.citation.raw_text[:40]}... -> {r.message}\n"

    return summary


def main():
    mcp.run()


if __name__ == "__main__":
    main()
