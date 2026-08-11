"""Unit tests for ReportGenerator (HTML and Markdown report generation)."""

import pytest
from academic_guardrail.core.reporter import ReportGenerator
from academic_guardrail.core.models import (
    Citation, ContextClaim, VerificationResult, VerificationStatus, RiskLevel, DocumentAuditReport
)


@pytest.fixture
def sample_report():
    cit = Citation(id="cit_1", raw_text="[1] Mortensen et al.", doi="10.1016/j.cell.2020.01.001", title="Sample Paper")
    claim = ContextClaim(citation_id="cit_1", claim_sentence="Metformin reduces mortality.", surrounding_context="Context text")
    res = VerificationResult(
        citation=cit,
        claim=claim,
        status=VerificationStatus.VALID,
        risk_level=RiskLevel.PASS,
        verified_title="Sample Paper Verified",
        verified_doi="10.1016/j.cell.2020.01.001",
        abstract_tldr="Metformin therapy decreased overall mortality.",
        message="🟢 验证通过"
    )
    return DocumentAuditReport(
        document_path="paper.docx",
        total_citations=1,
        passed_count=1,
        notice_count=0,
        warning_count=0,
        danger_count=0,
        results=[res]
    )


def test_generate_markdown(sample_report):
    generator = ReportGenerator()
    md_content = generator.generate_markdown(sample_report)
    assert "# 🛡️ 学术论文引用与断言审查报告" in md_content
    assert "paper.docx" in md_content
    assert "cit_1" in md_content


def test_generate_html(sample_report):
    generator = ReportGenerator()
    html_content = generator.generate_html(sample_report)
    assert "<!DOCTYPE html>" in html_content
    assert "paper.docx" in html_content
    assert "Sample Paper Verified" in html_content
