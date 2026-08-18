"""Model Context Protocol (MCP) Server for Academic Guardrail Agent."""

import functools
from typing import Optional
from mcp.server.fastmcp import FastMCP
from academic_guardrail.core.exceptions import (
    AcademicGuardrailError, ParserError, ProviderError, RateLimitError
)
from academic_guardrail.core.models import VerificationStatus

mcp = FastMCP("Academic Guardrail Agent")

# Lazy-initialized service — created on first tool call, NOT at import time.
# This prevents proxy scanning and stdout pollution during module load (critical for MCP stdio mode).
_service = None
_provider = None


def _get_service():
    """Returns the process-wide AuditService singleton, creating it lazily on first call."""
    global _service, _provider
    if _service is None:
        from academic_guardrail.core.service import AuditService
        _service = AuditService()
        _provider = _service.provider
    return _service


def _get_provider():
    _get_service()
    return _provider


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
async def verify_single_citation(citation_str_or_doi: str, detail: str = "compact") -> str:
    """验证单条文献引用的真实性、DOI 匹配及撤稿状态。
    支持 Progressive Disclosure 载荷调控 (detail: 'compact' | 'detailed' | 'debug')。
    """
    provider = _get_provider()
    is_doi = citation_str_or_doi.startswith("10.") or "doi.org" in citation_str_or_doi
    doi = citation_str_or_doi if is_doi else None
    title = citation_str_or_doi if not is_doi else ""

    res = await provider.verify_citation(title=title, doi=doi)
    detail_mode = (detail or "compact").lower()

    if res.get("is_retracted"):
        out = [
            "🔴 [DANGER/撤稿警示] 论文已被撤稿或发出学术预警！",
            f"标题: 《{res.get('title')}》",
            f"DOI: {res.get('doi')}",
            f"证据状态: {res.get('evidence_status', 'RETRACTED')}"
        ]
        if detail_mode in ["detailed", "debug"]:
            out.append(f"详细说明: {res.get('message', '')}")
        return "\n".join(out)
    elif res.get("matched"):
        conf_val = res.get("confidence", 0.0)
        abstract_snippet = res.get("abstract", "")[:200]
        out = [
            "🟢 [PASS/验证通过] 数据库成功查实匹配论文。",
            f"标题: 《{res.get('title')}》",
            f"DOI: {res.get('doi')}",
            f"证据状态: {res.get('evidence_status', 'ARTICLE_MATCHED')}"
        ]
        if detail_mode in ["detailed", "debug"]:
            res_meta = res.get("resolution_metadata") or {}
            out.extend([
                f"Reference Confidence: {conf_val:.2f}",
                f"消歧打分分解: Title={res_meta.get('title_score', 'N/A')}, Author={res_meta.get('author_score', 'N/A')}, Margin={res_meta.get('rank_margin', 'N/A')}",
                f"摘要片段: \"{abstract_snippet}...\""
            ])
        if detail_mode == "debug":
            out.append(f"数据源: {res.get('source')}")
        return "\n".join(out)
    else:
        failure_info = f" ({res.get('failure_reason')})" if res.get("failure_reason") else ""
        return f"🟡 [UNVERIFIED/未查证] 无法在数据库中核实该文献{failure_info}。说明: {res.get('message', '无')}"


@mcp.tool()
@handle_mcp_exceptions
async def check_paper_retraction(doi: str) -> str:
    """专门查询指定 DOI 论文是否存在撤稿记录。"""
    provider = _get_provider()
    res = await provider.verify_citation(title="", doi=doi)
    if res.get("is_retracted"):
        return f"🔴 [RETRACTED] 论文 {doi} 已被撤稿！来源: {res.get('source')}"
    elif res.get("matched"):
        return f"🟢 [NO_RETRACTION_FOUND] 论文 {doi} 状态正常，未发现撤稿记录。"
    elif res.get("evidence_status") == "PROVIDER_UNAVAILABLE":
        return f"🟡 [PROVIDER_UNAVAILABLE] 数据库暂时不可用 ({res.get('failure_reason')})，无法验证撤稿。"
    else:
        return f"🟡 [UNKNOWN] 未能检索到 DOI {doi} 的纪录。"


@mcp.tool()
@handle_mcp_exceptions
async def audit_document_claims(
    file_path: str,
    refs_dir: str = "",
    detail: str = "compact",
    output_html_path: str = ""
) -> str:
    """全面审计论文原稿（.pdf, .docx, .md, .tex），抽取引用真实性、撤稿记录，
    并提取正文断言与被引文献的精准证据片段。
    自动生成自包含 HTML 审查报告并保存在本地。
    支持 Progressive Disclosure 载荷控制 (detail: 'compact' | 'detailed' | 'debug')。
    """
    import os
    from academic_guardrail.core.reporter import ReportGenerator

    service = _get_service()
    report = await service.audit_document(file_path, refs_dir=refs_dir if refs_dir else None)

    if report.total_citations == 0:
        return "ℹ️ 未在文档中识别出任何文献引用标记或 GB/T 7714 格式。"

    # Auto-generate HTML report file
    if not output_html_path:
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        dir_name = os.path.dirname(os.path.abspath(file_path)) or os.getcwd()
        output_html_path = os.path.join(dir_name, f"{base_name}_audit_report.html")

    try:
        generator = ReportGenerator()
        html_content = generator.generate_html(report)
        with open(output_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        saved_msg = f"📁 自包含 HTML 审查报告已自动保存至: {os.path.abspath(output_html_path)}"
    except Exception as e:
        saved_msg = f"⚠️ HTML 报告保存失败: {e}"

    detail_mode = (detail or "compact").lower()

    output_lines = [
        f"📊 学术引用与原文对齐审计报告: {report.document_path} (Payload Detail: {detail_mode.upper()})",
        saved_msg,
        f"总引用数: {report.total_citations} | 🟢 吻合通过: {report.passed_count} | 🔵 补充提示: {report.notice_count} | 🟡 未查核警告: {report.warning_count} | 🔴 撤稿高危: {report.danger_count}\n",
        "--- 提炼对齐明细 (请宿主 Agent 评阅正文断言与文献原文对齐情况) ---"
    ]

    for item in report.results:
        cit = item.citation
        claim_text = item.claim.claim_sentence if item.claim else "无"
        evidence_text = item.evidence_text or item.abstract_tldr or "无摘要原文"
        granularity = item.evidence_granularity or "SENTENCE"

        if item.status == VerificationStatus.RETRACTED:
            status_flag = "🔴 撤稿高危"
        elif item.status == VerificationStatus.VALID:
            status_flag = "🟢 已查实"
        else:
            status_flag = "🟡 未查核"

        doi_str = f" | DOI: {item.verified_doi}" if item.verified_doi else ""
        ev_status_str = f" | EvidenceStatus: {item.evidence_status.value}" if item.evidence_status else ""

        line_info = [
            f"\n• [{cit.id}] {cit.raw_text[:60]}... ({status_flag}{doi_str}{ev_status_str})",
            f"  ├─ 正文断言: \"{claim_text}\"",
            f"  ├─ 证据原文 [{granularity}]: \"{evidence_text[:150]}...\"",
            f"  └─ 判定说明: {item.message}"
        ]

        if detail_mode in ["detailed", "debug"]:
            ref_conf_str = f"{item.reference_confidence:.2f}" if item.reference_confidence is not None else "N/A"
            align_score_str = f"{item.claim_alignment_score:.2f}" if item.claim_alignment_score is not None else "N/A"
            align_state_str = item.alignment_state or "UNVERIFIED"
            engine_str = f" ({item.alignment_engine})" if item.alignment_engine else ""
            line_info.insert(1, f"  ├─ Reference Confidence: {ref_conf_str}")
            line_info.insert(2, f"  ├─ Claim Alignment Score: {align_score_str}{engine_str}")
            line_info.insert(3, f"  ├─ Alignment State: {align_state_str}")

        if detail_mode == "debug" and item.resolution_metadata:
            line_info.append(f"  └─ 调试元数据: {item.resolution_metadata}")

        output_lines.extend(line_info)

    return "\n".join(output_lines)


@mcp.tool()
@handle_mcp_exceptions
async def generate_audit_html_report(file_path: str, output_path: str = "", refs_dir: str = "") -> str:
    """运行学术审计并直接输出自包含 HTML 报告（含 KaTeX、Sticky TOC、暗黑模式切换）。"""
    import os
    from academic_guardrail.core.reporter import ReportGenerator

    service = _get_service()
    report = await service.audit_document(file_path, refs_dir=refs_dir if refs_dir else None)

    if not output_path:
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        dir_name = os.path.dirname(os.path.abspath(file_path)) or os.getcwd()
        output_path = os.path.join(dir_name, f"{base_name}_audit_report.html")

    generator = ReportGenerator()
    html_content = generator.generate_html(report)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return f"✅ HTML 审查报告生成成功！\n文件绝对路径: {os.path.abspath(output_path)}\n包含引用总数: {report.total_citations} 项。"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
