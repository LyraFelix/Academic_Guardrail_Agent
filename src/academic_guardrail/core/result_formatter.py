"""Plain text presentation shared by CLI and MCP; no decision logic lives here."""

from academic_guardrail.core.models import Citation, VerificationResult
from academic_guardrail.core.ref_resolver import ReferenceResolver


def citation_from_text(text: str) -> Citation:
    """Accept a complete DOI/DOI URL or treat input as a title query."""
    value = text.strip()
    doi = ReferenceResolver.normalize_doi(value)
    return Citation(id="single", raw_text=value, doi=doi, title=None if doi else value)


def format_result(result: VerificationResult, detail: str = "compact") -> str:
    lines = [
        f"[{result.risk_level.value}/{result.status.value}] {result.message}",
        f"标题: {result.verified_title or result.citation.title or '未核实'}",
        f"DOI: {result.verified_doi or result.citation.doi or '未提供'}",
        f"证据状态: {result.evidence_status.value if result.evidence_status else '未指定'}",
        f"撤稿状态: {result.retraction_status.value}",
        f"核验范围: {result.verification_scope}",
    ]
    if result.failure_reason:
        lines.append(f"查询异常: {result.failure_reason}")
    if result.retraction_info:
        lines.append(f"撤稿说明: {result.retraction_info}")
    for source in result.sources:
        lines.append(f"数据源: {source.source} [{source.kind}] {source.identifier or ''} {source.detail or ''}")
    if result.claim:
        lines.append(f"正文断言: {result.claim.claim_sentence}")
    if result.evidence_text:
        text = result.evidence_text
        if detail == "compact" and len(text) > 200:
            text = text[:200] + "…（已截断，detailed 可查看完整片段）"
        lines.append(f"证据原文 [{result.evidence_granularity or 'TEXT'}]: {text}")
    if detail in {"detailed", "debug"}:
        if result.reference_confidence is not None:
            lines.append(f"Reference Confidence: {result.reference_confidence:.2f}（匹配分数，非正确率）")
        if result.claim_alignment_score is not None:
            lines.append(f"Claim Alignment Score: {result.claim_alignment_score:.2f} ({result.alignment_engine})")
        lines.append(f"Alignment State: {result.alignment_state or 'NOT_EVALUATED'}")
        if result.resolution_metadata:
            lines.append(f"消歧打分分解: {result.resolution_metadata}")
        if result.ambiguous_candidates:
            lines.append(f"歧义候选: {result.ambiguous_candidates}")
    if detail == "debug":
        lines.append(f"调试元数据: {result.model_dump(mode='json')}")
    return "\n".join(lines)
