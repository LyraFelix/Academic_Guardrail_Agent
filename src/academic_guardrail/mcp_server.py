"""Model Context Protocol (MCP) Server for Academic Guardrail Agent."""

import functools
from typing import Literal
from mcp.server.fastmcp import FastMCP
from academic_guardrail.core.review_models import ClientJudgment
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
        "客户端后续步骤：本地规则不是最终语义判断。对正文断言使用 prepare_claim_review 准备完整证据，"
        "读取所有证据页后自行分析，再用 record_claim_review 核对引用并保存模型判断；不要仅因规则弃判就要求用户人工复核。",
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


@mcp.tool()
async def prepare_claim_review(claim: str, reference_text: str = "", citation_str_or_doi: str = "",
                               refs_dir: str = "", offline: bool = True) -> dict:
    """为客户端模型准备正文断言的证据包。reference_text 与 citation_str_or_doi 必须二选一。

    返回完整证据句、位置、文献身份、本地规则提示和分页信息。客户端继续判断语义，
    然后调用 record_claim_review；规则弃判不是要求用户接管。提供的裸文本不核验文献身份。
    """
    from academic_guardrail.core.claim_review import build_review_packet, packet_response
    from academic_guardrail.core.models import EvidencePassage
    from academic_guardrail.core.ref_store import LocalRefStore
    from academic_guardrail.core.result_formatter import citation_from_text
    from academic_guardrail.core.review_store import ReviewStore

    if bool(reference_text.strip()) == bool(citation_str_or_doi.strip()):
        raise ValueError("Provide exactly one of reference_text or citation_str_or_doi")
    if reference_text.strip():
        if refs_dir:
            raise ValueError("refs_dir belongs to citation lookup, not provided text")
        packet = build_review_packet(claim, [EvidencePassage(text=reference_text, source_kind="PROVIDED_TEXT")])
    else:
        service = _get_service(offline=offline)
        try:
            store = LocalRefStore(refs_dir) if refs_dir else None
            packet = await service.prepare_client_review(citation_from_text(citation_str_or_doi), claim, store)
        finally:
            await service.close()
    digest = ReviewStore().save_packet(packet)
    return packet_response(packet, digest)


@mcp.tool()
async def read_claim_evidence(packet_id: str, offset: int = 0, limit: int = 24) -> dict:
    """继续读取已保存证据包的完整原文句子。按 next_offset 翻页，不重新联网检索。"""
    from academic_guardrail.core.claim_review import evidence_page
    from academic_guardrail.core.review_store import ReviewStore, content_digest
    packet = ReviewStore().load_packet(packet_id)
    return {**evidence_page(packet, offset, limit),
            "packet_sha256": content_digest(packet.model_dump(mode="json"))}


@mcp.tool()
async def record_claim_review(packet_id: str, judgment: ClientJudgment, expected_packet_sha256: str) -> dict:
    """校验证据编号、完整阅读声明和逐字引用，保存客户端模型的结构化语义判断。

    SUPPORTED/CONTRADICTED 至少需要一条原文引用；确定结论须声明考虑全部证据。
    expected_packet_sha256 使用准备证据包时返回的摘要，确保提交时证据没有变化。
    可选 suggested_revision 给出有引用的改写建议；不改变原论断结论，也不认证改写语义。
    校验通过只表示引用与记录一致，不证明模型推理正确。每次提交生成新记录。
    """
    from academic_guardrail.core.review_store import ReviewStore
    return ReviewStore().record(packet_id, judgment, expected_packet_sha256)


def _local_packet_response(packet) -> dict:
    from academic_guardrail.core.claim_review import packet_response
    from academic_guardrail.core.review_store import ReviewStore, content_digest
    context = ReviewStore().load_context(packet.packet_id)
    return {**packet_response(packet, content_digest(packet.model_dump(mode="json"))),
            "local_review": context.model_dump(mode="json")}


@mcp.tool()
async def prepare_local_claim_review(claim: str, citation_str_or_doi: str, refs_dir: str,
                                     initial_scope: Literal["abstract", "full_text"] = "abstract") -> dict:
    """从同一篇身份匹配的本地文献准备摘要证据，保存文件指纹；全程离线。

    initial_scope 为 abstract 或 full_text。没有摘要时明确返回空证据，不伪造摘要。
    客户端记录判断及 missing_evidence 后，可对该文献进行一次定向补查。
    """
    from academic_guardrail.core.local_review import prepare_local_review
    return _local_packet_response(await prepare_local_review(claim, citation_str_or_doi, refs_dir, initial_scope))


@mcp.tool()
async def follow_up_local_claim(review_id: str, expected_review_sha256: str, gap_index: int = 0) -> dict:
    """按已保存的证据缺口在同一篇本地文献中补查一次，返回新证据包。

    使用 record_claim_review 返回的 review_sha256；原文变化、明确结论或重复补查会拒绝。
    命中只是候选原文。客户端须读取新包全部分页、重新判断并再次保存。
    """
    from academic_guardrail.core.local_review import follow_up_review
    return _local_packet_response(follow_up_review(review_id, expected_review_sha256, gap_index))


@mcp.tool()
async def generate_claim_review_report(review_ids: list[str], output_path: str) -> dict:
    """把指定判断及其补查前记录导出自包含 HTML，显示原文位置和结论变化。

    报告保存时检查来源文件是否变化；不把引用校验或标签变化当成科学正确性认证。
    使用新的 .html 路径，不能覆盖原文件或已有报告。
    """
    from academic_guardrail.core.followup_report import save_review_report
    from academic_guardrail.core.review_store import ReviewStore
    return save_review_report(ReviewStore(), review_ids, output_path)


@mcp.prompt()
def review_claim_workflow(claim: str, citation: str = "", refs_dir: str = "", output_path: str = "") -> str:
    """让客户端完成取证、语义判断、反证检查和引用校验的完整流程。"""
    import json
    from academic_guardrail.core.claim_review import REVIEW_INSTRUCTIONS
    if refs_dir:
        workflow = ("\nFirst call prepare_local_claim_review with the supplied claim, citation and refs_dir, "
                    "using initial_scope=abstract. Read every page with read_claim_evidence, then record "
                    "your judgment and any specific missing_evidence. If unresolved and a gap is recorded, "
                    "call follow_up_local_claim once with that review_id, review_sha256 and selected gap. "
                    "Read the entire extended packet and record a fresh judgment using its new digest. ")
    else:
        workflow = ("\nFirst call prepare_claim_review with the supplied claim and citation, "
                    "or with source text the user supplied. Follow next_offset with read_claim_evidence. ")
    if output_path:
        workflow += ("After recording, call generate_claim_review_report with the final saved review_id "
                     "and supplied output_path; its local parent is included automatically. ")
    workflow += ("Report the client conclusion, exact quotes, source scope, any suggested revision, "
                 "and remaining limitations. A changed verdict is not proof of improvement.\n")
    # User text is serialized as data, separate from the workflow instructions.
    task = {"claim": claim, "citation": citation, "refs_dir": refs_dir, "output_path": output_path}
    return REVIEW_INSTRUCTIONS + workflow + "Task data: " + json.dumps(task, ensure_ascii=False)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
