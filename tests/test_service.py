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
