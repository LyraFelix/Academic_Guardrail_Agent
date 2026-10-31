"""Model Context Protocol (MCP) Server for Academic Guardrail Agent."""

import functools
from mcp.server.fastmcp import FastMCP
from academic_guardrail.core.exceptions import (
    AcademicGuardrailError, ParserError, ProviderError, RateLimitError
)

mcp = FastMCP("Academic Guardrail Agent")

def _get_service(offline: bool = False):
    """Create one service per invocation; callers close it in a finally block."""
    from academic_guardrail.core.service import AuditService
    return AuditService(offline=offline)


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
async def verify_single_citation(citation_str_or_doi: str, detail: str = "compact", offline: bool = False) -> str:
    """核验文献身份和撤稿证据。offline=True 禁止在线查询及模型加载。"""
    from academic_guardrail.core.result_formatter import citation_from_text, format_result
    service = _get_service(offline=offline)
    try:
        result = await service.verify_reference(citation_from_text(citation_str_or_doi))
        return format_result(result, detail)
    finally:
        await service.close()


@mcp.tool()
@handle_mcp_exceptions
async def check_paper_retraction(doi: str, offline: bool = False) -> str:
    """查询 DOI 的撤稿证据。NO_RECORD 仅表示已查来源无记录，不代表状态正常。"""
    return await verify_single_citation(doi, detail="detailed", offline=offline)


def _save_html(report, file_path: str, output_path: str) -> str:
    from pathlib import Path
    from academic_guardrail.core.reporter import ReportGenerator
    source = Path(file_path).resolve()
    destination = Path(output_path).resolve() if output_path else source.with_name(source.stem + "_audit_report.html")
    if destination == source:
        raise ValueError("报告路径不能覆盖输入原稿")
    destination.write_text(ReportGenerator().generate_html(report), encoding="utf-8")
    return str(destination)


@mcp.tool()
@handle_mcp_exceptions
async def audit_document_claims(file_path: str, refs_dir: str = "", detail: str = "compact",
                                output_html_path: str = "", offline: bool = False) -> str:
    """抽取引用，核验元数据和撤稿线索，执行启发式文本比对并输出离线 HTML。"""
    from academic_guardrail.core.result_formatter import format_result, format_counts, format_diagnostic
    service = _get_service(offline=offline)
    try:
        report = await service.audit_document(file_path, refs_dir=refs_dir or None)
    finally:
        await service.close()
    saved = _save_html(report, file_path, output_html_path)
    lines = [
        f"学术引用审查: {report.document_path} (Payload Detail: {detail.upper()})",
        f"HTML 报告: {saved}",
        f"模式: {'离线' if report.offline else '在线'}；{format_counts(report)}；"
        f"通过: {report.passed_count}；提示: {report.notice_count}；警告: {report.warning_count}；高危: {report.danger_count}",
        "零引用意味着未识别到可核验条目；文本相似度不等于事实支持。",
    ]
    lines.extend(format_diagnostic(item) for item in report.parse_diagnostics)
    lines.extend(format_result(item, detail) for item in report.results)
    return "\n\n".join(lines)


@mcp.tool()
@handle_mcp_exceptions
async def generate_audit_html_report(file_path: str, output_path: str = "", refs_dir: str = "",
                                      offline: bool = False) -> str:
    """运行引用核验，生成无需 CDN 的自包含 HTML 报告。"""
    service = _get_service(offline=offline)
    try:
        report = await service.audit_document(file_path, refs_dir=refs_dir or None)
    finally:
        await service.close()
    saved = _save_html(report, file_path, output_path)
    from academic_guardrail.core.result_formatter import format_counts, format_diagnostic
    return f"HTML 审查报告: {saved}\n{format_counts(report)}\n" + "\n".join(format_diagnostic(item) for item in report.parse_diagnostics)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
