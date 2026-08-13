import pytest

pytest.importorskip("mcp.server.fastmcp")

from unittest.mock import AsyncMock, patch
from academic_guardrail.mcp_server import verify_single_citation, audit_document_claims


@pytest.mark.asyncio
async def test_verify_single_citation_compact():
    mock_res = {
        "matched": True,
        "title": "Test Paper Title",
        "doi": "10.1000/182",
        "is_retracted": False,
        "confidence": 0.95,
        "evidence_status": "ARTICLE_MATCHED",
        "resolution_metadata": {"title_score": 1.0, "rank_margin": 0.5},
        "abstract": "This is a full abstract for testing purposes."
    }

    with patch("academic_guardrail.mcp_server._get_provider") as mock_get:
        provider = AsyncMock()
        provider.verify_citation = AsyncMock(return_value=mock_res)
        mock_get.return_value = provider

        # 1. Compact mode (Default)
        res_compact = await verify_single_citation("Test Paper Title", detail="compact")
        assert "🟢 [PASS/验证通过]" in res_compact
        assert "消歧打分分解" not in res_compact

        # 2. Detailed mode
        res_detailed = await verify_single_citation("Test Paper Title", detail="detailed")
        assert "🟢 [PASS/验证通过]" in res_detailed
        assert "消歧打分分解" in res_detailed
        assert "Reference Confidence: 0.95" in res_detailed

        # 3. Debug mode
        res_debug = await verify_single_citation("Test Paper Title", detail="debug")
        assert "数据源:" in res_debug


@pytest.mark.asyncio
async def test_audit_document_claims_progressive_disclosure(tmp_path):
    doc = tmp_path / "test.txt"
    doc.write_text("AI improves productivity [1].\n\n[1] Author. Paper Title[J]. 2023.", encoding="utf-8")

    from academic_guardrail.core.models import (
        DocumentAuditReport, VerificationResult, Citation, ContextClaim, VerificationStatus, RiskLevel, EvidenceStatus
    )

    cit = Citation(id="cit_1", raw_text="[1] Author. Paper Title[J]. 2023.", title="Paper Title")
    claim = ContextClaim(citation_id="cit_1", claim_sentence="AI improves productivity", surrounding_context="")
    item = VerificationResult(
        citation=cit,
        claim=claim,
        status=VerificationStatus.VALID,
        risk_level=RiskLevel.PASS,
        evidence_status=EvidenceStatus.ARTICLE_MATCHED,
        evidence_text="AI significantly boosts efficiency.",
        evidence_granularity="SENTENCE",
        reference_confidence=0.95,
        claim_alignment_score=0.90,
        alignment_state="SUPPORTED",
        alignment_engine="vector_embedding",
        resolution_metadata={"title_score": 1.0, "rank_margin": 0.5},
        message="🟢 高度一致"
    )
    mock_report = DocumentAuditReport(
        document_path=str(doc),
        total_citations=1,
        passed_count=1,
        warning_count=0,
        danger_count=0,
        results=[item]
    )

    with patch("academic_guardrail.mcp_server._get_service") as mock_get:
        service = AsyncMock()
        service.audit_document = AsyncMock(return_value=mock_report)
        mock_get.return_value = service

        # Compact
        out_compact = await audit_document_claims(str(doc), detail="compact")
        assert "Payload Detail: COMPACT" in out_compact
        assert "Claim Alignment Score" not in out_compact

        # Detailed
        out_detailed = await audit_document_claims(str(doc), detail="detailed")
        assert "Payload Detail: DETAILED" in out_detailed
        assert "Claim Alignment Score: 0.90 (vector_embedding)" in out_detailed

        # Debug
        out_debug = await audit_document_claims(str(doc), detail="debug")
        assert "调试元数据" in out_debug
