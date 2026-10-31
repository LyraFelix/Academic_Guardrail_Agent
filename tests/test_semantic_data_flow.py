"""Rule findings retain source coordinates and identical meaning at every output."""

import pytest

from academic_guardrail.core.models import (
    Citation, ContextClaim, DocumentAuditReport, EvidencePassage, RetractionStatus,
    RiskLevel, SourceLocation, VerificationResult, VerificationStatus,
)
from academic_guardrail.core.reporter import ReportGenerator
from academic_guardrail.core.result_formatter import format_result
from academic_guardrail.core.service import AuditService, PreparedReference


def prepare(texts, *, retracted=False):
    citation = Citation(id="1", raw_text="Synthetic study", title="Synthetic study")
    result = VerificationResult(citation=citation,
                                status=VerificationStatus.RETRACTED if retracted else VerificationStatus.VALID,
                                risk_level=RiskLevel.DANGER if retracted else RiskLevel.PASS,
                                retraction_status=RetractionStatus.CONFIRMED if retracted else RetractionStatus.NOT_CHECKED,
                                message="Matched local metadata.")
    passages = [EvidencePassage(text=text, source_kind="LOCAL_FULLTEXT", location=SourceLocation(
        file_path="synthetic.txt", page=i + 1, line=1, char_start=i * 100, char_end=i * 100 + len(text)))
        for i, text in enumerate(texts)]
    return PreparedReference(result, passages)


def evaluate(texts, claim="Treatment improves survival.", **kwargs):
    service = AuditService(offline=True)
    return service._evaluate_occurrence(prepare(texts, **kwargs), ContextClaim(
        citation_id="1", claim_sentence=claim, surrounding_context=""))


def test_wording_alignment_is_notice_never_green_claim_pass():
    result = evaluate(["Treatment improves survival."])
    assert result.alignment_state == "TEXT_ALIGNED"
    assert result.risk_level == RiskLevel.NOTICE
    assert result.verification_scope == "RULE_BASED_REVIEW"


def test_numeric_conflict_keeps_score_and_exact_source():
    evidence = "Background. Treatment reduces mortality by 10%."
    result = evaluate([evidence], "Treatment reduces mortality by 90%.")
    assert result.alignment_state == "POTENTIAL_CONFLICT"
    assert result.risk_level == RiskLevel.WARNING
    assert result.claim_alignment_score > 0.5  # Retrieval remains similar despite the conflict.
    item = next(f for f in result.semantic_findings if f.code == "NUMBER_MISMATCH")
    loc = item.evidence_location
    assert evidence[loc.char_start:loc.char_end] == item.evidence_text
    assert item.evidence_text == "Treatment reduces mortality by 10%."


def test_conflicting_pages_are_both_kept_for_review():
    result = evaluate(["Treatment improves survival.", "Treatment does not improve survival."])
    assert result.alignment_state == "REVIEW_REQUIRED"
    assert result.risk_level == RiskLevel.NOTICE
    items = [f for f in result.semantic_findings if f.code == "EVIDENCE_DISAGREEMENT"]
    assert {f.evidence_location.page for f in items} == {1, 2}
    assert {f.evidence_text for f in items} == {"Treatment improves survival.", "Treatment does not improve survival."}


def test_retraction_precedes_semantic_alignment():
    result = evaluate(["Treatment improves survival."], retracted=True)
    assert result.risk_level == RiskLevel.DANGER
    assert result.status == VerificationStatus.RETRACTED
    assert result.alignment_state is None


def test_two_different_numbers_in_evidence_require_review():
    result = evaluate(["Treatment reduces mortality by 20%.", "Treatment reduces mortality by 30%."],
                      "Treatment reduces mortality by 10%.")
    assert result.alignment_state == "REVIEW_REQUIRED"
    assert {f.evidence_location.page for f in result.semantic_findings if f.code == "EVIDENCE_DISAGREEMENT"} == {1, 2}


def test_online_finding_does_not_borrow_local_coordinates():
    prepared = prepare(["Treatment reduces mortality by 20%."])
    prepared.passages.append(EvidencePassage(text=prepared.passages[0].text, source_kind="ONLINE_ABSTRACT"))
    result = AuditService(offline=True)._evaluate_occurrence(prepared, ContextClaim(
        citation_id="1", claim_sentence="Treatment reduces mortality by 10%.", surrounding_context=""))
    online = [f for f in result.semantic_findings if f.evidence_source == "ONLINE_ABSTRACT"]
    assert online and all(f.evidence_location is None for f in online)


def test_no_text_has_explicit_insufficient_state():
    result = evaluate([])
    assert result.alignment_state == "INSUFFICIENT_EVIDENCE"
    assert result.retrieval_status == "NO_TEXT"
    assert result.risk_level == RiskLevel.NOTICE


def test_html_markdown_and_plaintext_show_same_findings_safely():
    result = evaluate(["Treatment reduces mortality by 10%."], "Treatment reduces mortality by 90%.")
    result.semantic_findings[0].message += " <script>alert(1)</script>"
    report = DocumentAuditReport(document_path="draft.txt", total_citations=1,
                                 passed_count=0, warning_count=1, danger_count=0, results=[result])
    for output in [format_result(result), ReportGenerator().generate_html(report),
                   ReportGenerator().generate_markdown(report)]:
        assert "NUMBER_MISMATCH" in output
        assert "POTENTIAL_CONFLICT" in output
        assert "10%" in output and "90%" in output
        assert "synthetic.txt" in output
    assert "<script>alert(1)</script>" not in ReportGenerator().generate_html(report)
    assert "<script>alert(1)</script>" not in ReportGenerator().generate_markdown(report)


def test_embedding_retrieval_cannot_override_numeric_check(monkeypatch):
    service = AuditService(offline=True)
    monkeypatch.setattr(service.evaluator.semantic_matcher, "compute_similarity_with_engine",
                        lambda a, b: (1.0, "vector_embedding"))
    result = service._evaluate_occurrence(prepare(["The dose was 5 mg."]), ContextClaim(
        citation_id="1", claim_sentence="The dose was 50 mg.", surrounding_context=""))
    assert result.alignment_state == "POTENTIAL_CONFLICT"
    assert result.risk_level == RiskLevel.WARNING
