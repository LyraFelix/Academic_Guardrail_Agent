"""Unit tests for AuditService core business logic layer."""

import pytest
import asyncio
from academic_guardrail.core.service import AuditService
from academic_guardrail.core.models import RiskLevel


class TestAuditService:

    @pytest.fixture
    def service(self):
        return AuditService(max_concurrency=5, request_timeout=10.0)

    def test_audit_service_initialization(self, service):
        assert service.max_concurrency == 5
        assert service.request_timeout == 10.0

    def test_audit_document_nonexistent_file(self, service):
        with pytest.raises(FileNotFoundError):
            asyncio.run(service.audit_document("/nonexistent/path/file.docx"))

    def test_audit_document_text_file(self, service, tmp_path):
        content = (
            "人工智能能够显著提升企业生产效率[1]。\n\n"
            "[1] 姚加权, 冯展斌. 人工智能如何提升企业生产效率[J]. 经济研究, 2023.\n"
        )
        file_p = tmp_path / "test_doc.txt"
        file_p.write_text(content, encoding="utf-8")

        report = asyncio.run(service.audit_document(str(file_p)))
        assert report.total_citations == 1
        assert len(report.results) == 1
        assert report.results[0].citation.id == "cit_1"
        assert report.results[0].reference_confidence is not None

    def test_audit_single_item_retracted(self, service):
        from unittest.mock import AsyncMock, patch
        from academic_guardrail.core.models import Citation, ContextClaim, VerificationStatus

        cit = Citation(id="cit_retracted", raw_text="[1] Retracted Author. Retracted Study[J]. 2020.", title="Retracted Study", doi="10.1016/j.cell.2006.02.001")
        claim = ContextClaim(citation_id="cit_retracted", claim_sentence="The study claims significant progress.", surrounding_context="")

        mock_res = {
            "matched": True,
            "title": "Retracted Study",
            "doi": "10.1016/j.cell.2006.02.001",
            "is_retracted": True,
            "confidence": 1.0
        }

        with patch.object(service.provider, "verify_citation", AsyncMock(return_value=mock_res)):
            res = asyncio.run(service.verify_single_item(cit, claim))

        assert res.status == VerificationStatus.RETRACTED
        assert res.risk_level == RiskLevel.DANGER
        assert res.alignment_state is None
        assert res.nli_state is None
        assert "撤稿" in res.message

    def test_audit_single_item_provider_unavailable(self, service):
        from unittest.mock import AsyncMock, patch
        from academic_guardrail.core.models import Citation, ContextClaim, VerificationStatus, EvidenceStatus

        cit = Citation(id="cit_timeout", raw_text="[1] Timeout Paper.", title="Timeout Paper")
        claim = ContextClaim(citation_id="cit_timeout", claim_sentence="Testing timeout.", surrounding_context="")

        mock_res = {
            "matched": None,
            "title": "Timeout Paper",
            "is_retracted": False,
            "confidence": 0.0,
            "evidence_status": "PROVIDER_UNAVAILABLE",
            "failure_reason": "TIMEOUT",
            "message": "🟡 数据源暂时不可用 (TIMEOUT)"
        }

        with patch.object(service.provider, "verify_citation", AsyncMock(return_value=mock_res)):
            res = asyncio.run(service.verify_single_item(cit, claim))

        assert res.status == VerificationStatus.UNVERIFIED
        assert res.evidence_status == EvidenceStatus.PROVIDER_UNAVAILABLE
        assert res.failure_reason == "TIMEOUT"
        assert res.risk_level == RiskLevel.WARNING
