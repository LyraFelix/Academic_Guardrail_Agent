"""Model Context Protocol (MCP) Server for Academic Guardrail Agent."""

import functools
from mcp.server.fastmcp import FastMCP
from academic_guardrail.core.service import AuditService
from academic_guardrail.core.exceptions import (
    AcademicGuardrailError, ParserError, ProviderError, RateLimitError
)

mcp = FastMCP("Academic Guardrail Agent")
service = AuditService()
provider = service.provider


def handle_mcp_exceptions(func):
    """Global exception middleware decorator for MCP Tool Handlers.
    Prevents unhandled crashes and returns structured, LLM-friendly error descriptions.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except RateLimitError as e:
            return f"🟡 [MCP RATE_LIMIT] 触发数据库速率限制 (HTTP 429): {e}"
        except ProviderError as e:
            return f"🟡 [MCP PROVIDER_ERROR] 学术数据库联网查询失败: {e}"
        except ParserError as e:
            return f"❌ [MCP PARSER_ERROR] 文档解析失败: {e}"
        except AcademicGuardrailError as e:
            return f"⚠️ [MCP ERROR] 审计逻辑执行失败: {e}"
        except FileNotFoundError as e:
            return f"❌ [MCP FILE_NOT_FOUND] 未找到指定文件: {e}"
        except Exception as e:
            return f"❌ [MCP UNHANDLED_ERROR] 发生未知服务异常: {str(e)}"
    return wrapper


@mcp.tool()
@handle_mcp_exceptions
async def verify_single_citation(citation_str_or_doi: str) -> str:
    """验证单条文献引用的真实性、DOI 匹配及撤稿状态。
    返回确定性的数据库元数据与检索结果，供 AI Agent 上下文直接评阅。
    """
    is_doi = citation_str_or_doi.startswith("10.") or "doi.org" in citation_str_or_doi
    doi = citation_str_or_doi if is_doi else None
    title = citation_str_or_doi if not is_doi else ""

    res = await provider.verify_citation(title=title, doi=doi)

    if res.get("is_retracted"):
        return (
            f"🔴 [DANGER/撤稿警示] 论文已被撤稿或发出学术预警！\n"
            f"标题: 《{res.get('title')}》\n"
            f"DOI: {res.get('doi')}\n"
            f"状态: 严重合规风险"
        )
    elif res.get("matched"):
        abstract_snippet = res.get("abstract", "")[:200]
        conf_val = res.get("confidence", 0.0)
        res_meta = res.get("resolution_metadata") or {}
        meta_info = f"\n消歧分解: Title: {res_meta.get('title_score', 'N/A')}, Author: {res_meta.get('author_score', 'N/A')}, Margin: {res_meta.get('rank_margin', 'N/A')}" if res_meta else ""
        return (
            f"🟢 [PASS/验证通过] 数据库成功查实匹配论文。\n"
            f"标题: 《{res.get('title')}》\n"
            f"DOI: {res.get('doi')}\n"
            f"Reference Confidence: {conf_val:.2f}{meta_info}\n"
            f"摘要片段: \"{abstract_snippet}...\""
        )
    else:
        return f"🟡 [WARNING/未查证] 无法在数据库中核实该文献，请检查拼写或格式 (输入: {citation_str_or_doi})"


@mcp.tool()
@handle_mcp_exceptions
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
@handle_mcp_exceptions
async def audit_document_claims(file_path: str, refs_dir: str = "") -> str:
    """全面审计论文原稿（.pdf, .docx, .md, .tex），抽取引用真实性、撤稿记录，
    并提取正文断言与被引文献的精准单句原文，透传给 AI Agent 在对话中做对齐判定。
    """
    report = await service.audit_document(file_path, refs_dir=refs_dir if refs_dir else None)

    if report.total_citations == 0:
        return "ℹ️ 未在文档中识别出任何文献引用标记或 GB/T 7714 格式。"

    output_lines = [
        f"📊 学术引用与原文对齐审计报告: {report.document_path}",
        f"总引用数: {report.total_citations} | 🟢 吻合通过: {report.passed_count} | 🔵 补充提示: {report.notice_count} | 🟡 未查核警告: {report.warning_count} | 🔴 撤稿高危: {report.danger_count}\n",
        "--- 提炼对齐明细 (请宿主 Agent 评阅正文断言与文献原文对齐情况) ---"
    ]

    for item in report.results:
        cit = item.citation
        claim_text = item.claim.claim_sentence if item.claim else "无"
        evidence_text = item.abstract_tldr or "无摘要原文"

        status_flag = "🔴 撤稿高危" if item.status == "RETRACTED" else ("🟢 已查实" if item.status == "VALID" else "🟡 未查核")
        doi_str = f" | DOI: {item.verified_doi}" if item.verified_doi else ""
        
        ref_conf_str = f"{item.reference_confidence:.2f}" if item.reference_confidence is not None else "N/A"
        align_score_str = f"{item.claim_alignment_score:.2f}" if item.claim_alignment_score is not None else "N/A"
        align_state_str = item.alignment_state or "UNVERIFIED"
        engine_str = f" ({item.alignment_engine})" if item.alignment_engine else ""

        line_info = [
            f"\n• [{cit.id}] {cit.raw_text[:60]}... ({status_flag}{doi_str})",
            f"  ├─ Reference Confidence: {ref_conf_str}",
            f"  ├─ Claim Alignment Score: {align_score_str}{engine_str}",
            f"  ├─ Alignment State: {align_state_str}",
            f"  ├─ 正文断言: \"{claim_text}\"",
            f"  ├─ 文献单句原文: \"{evidence_text[:150]}...\"",
            f"  └─ 数据库说明: {item.message}"
        ]
        output_lines.extend(line_info)

    return "\n".join(output_lines)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
