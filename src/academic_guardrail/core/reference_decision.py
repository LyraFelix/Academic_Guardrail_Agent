"""Pure reference decisions shared by document, CLI and MCP entry points.

Providers collect observations; this module alone assigns reference risk. Keeping
I/O outside this function makes the precedence rules easy to read and test.
"""

from typing import Any, Dict

from academic_guardrail.core.models import (
    Citation, EvidenceStatus, RetractionStatus, RiskLevel,
    VerificationResult, VerificationStatus,
)


def decide_reference(citation: Citation, evidence: Dict[str, Any]) -> VerificationResult:
    """Resolve identity before attaching retraction facts to the cited paper."""
    uncertain = evidence.get("is_uncertain") or evidence.get("match_confidence") == "UNCERTAIN"
    retraction = evidence.get("retraction_status", "NOT_CHECKED")
    if evidence.get("is_retracted"):
        retraction = "CONFIRMED"
    elif evidence.get("retraction_suspected"):
        retraction = "SUSPECTED"
    if retraction == "CONFIRMED" and not evidence.get("matched"):
        uncertain = True

    status = VerificationStatus.UNVERIFIED
    risk = RiskLevel.WARNING
    evidence_status = evidence.get("evidence_status") or EvidenceStatus.NOT_FOUND
    message = "未能核实该文献，请检查标题、作者或 DOI。"

    if uncertain:
        evidence_status = EvidenceStatus.AMBIGUOUS
        retraction = "NOT_CHECKED"
        message = "候选文献存在歧义，无法确定引用对象；候选的撤稿记录不能直接归属于当前引用。请补全 DOI 或作者。"
    elif retraction == "CONFIRMED":
        status = VerificationStatus.RETRACTED
        risk = RiskLevel.DANGER
        evidence_status = EvidenceStatus.RETRACTED
        message = "匹配到撤稿记录，请核对下列来源及撤稿说明。"
    elif retraction == "SUSPECTED":
        evidence_status = EvidenceStatus.RETRACTION_SUSPECTED
        message = "发现撤稿相关线索，尚未确认这是被撤稿论文。请查看来源并人工核验。"
    elif evidence.get("matched"):
        status = VerificationStatus.VALID
        risk = RiskLevel.PASS
        evidence_status = (EvidenceStatus.LOCAL_MATCHED if evidence_status == "LOCAL_MATCHED"
                           else EvidenceStatus.ARTICLE_MATCHED)
        message = ("已匹配本地文献文件；本地文本不能证明出版或当前撤稿状态。"
                   if evidence_status == EvidenceStatus.LOCAL_MATCHED
                   else "已匹配文献元数据；尚未判断正文断言是否成立。")
    elif evidence_status == "JOURNAL_MATCHED_ARTICLE_UNVERIFIED":
        risk = RiskLevel.NOTICE
        message = "仅识别到期刊名称，尚未核实具体文章。"
    elif evidence.get("failure_reason"):
        evidence_status = EvidenceStatus.PROVIDER_UNAVAILABLE
        message = "数据源暂时不可用；查询失败不能作为文献不存在的证据。"
    elif evidence_status == "OFFLINE_NO_MATCH":
        message = "离线模式未匹配到本地文献，未执行在线真实性核验。"

    if retraction == "NO_RECORD":
        message += " 在已查询来源中未发现撤稿记录，这不等于确认未撤稿。"
    elif retraction == "NOT_CHECKED":
        message += " 撤稿状态尚未核实。"

    # Unmatched metadata is a search candidate, not a verified title/abstract.
    matched = bool(evidence.get("matched")) and not uncertain
    abstract = evidence.get("abstract") if matched else None
    return VerificationResult(
        citation=citation, status=status, risk_level=risk,
        evidence_status=evidence_status, retraction_status=RetractionStatus(retraction),
        sources=evidence.get("sources") or [], failure_reason=evidence.get("failure_reason"),
        verified_title=evidence.get("title") if matched else None,
        verified_doi=evidence.get("doi") if matched else None,
        retraction_info=evidence.get("retraction_info"),
        abstract_tldr=abstract, evidence_text=abstract,
        evidence_granularity="FULL_ABSTRACT" if abstract else None,
        reference_confidence=evidence.get("confidence", 0.0),
        resolution_metadata=evidence.get("resolution_metadata"),
        ambiguous_candidates=evidence.get("ambiguous_candidates") if uncertain else None,
        message=message,
    )
