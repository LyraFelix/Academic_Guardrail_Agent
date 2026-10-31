"""Document-level counts and per-reference lookup reuse."""

from unittest.mock import AsyncMock

import pytest

from academic_guardrail.core.service import AuditService


@pytest.mark.asyncio
async def test_repeated_occurrences_reuse_metadata_but_not_mutable_results(tmp_path):
    path = tmp_path / "manuscript.md"
    path.write_text("Treatment improves survival [1]. Treatment reduces survival [1].\nReferences\n[1] Smith. A clinical trial[J]. 2024.\n[2] Jones. An uncited paper[J]. 2023.", encoding="utf-8")
    service = AuditService()
    service.provider.verify_citation = AsyncMock(return_value={"matched": True, "abstract": "Treatment improves survival.", "confidence": 1.0})
    try:
        report = await service.audit_document(str(path))
        assert service.provider.verify_citation.await_count == 2
        assert report.total_references == 2
        assert report.total_occurrences == 2
        assert report.total_citations == len(report.results) == 3
        first, second, uncited = report.results
        assert first.claim is not second.claim
        assert "improves" in first.claim.claim_sentence
        assert "reduces" in second.claim.claim_sentence
        # Different per-occurrence scores demonstrate independent evaluation;
        # phase two does not assert the heuristic's semantic classification.
        assert first.claim_alignment_score != second.claim_alignment_score
        assert uncited.claim is None
        assert uncited.verification_scope == "REFERENCE_METADATA"
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_missing_reference_does_not_trigger_provider_query(tmp_path):
    path = tmp_path / "missing.md"
    path.write_text("A claim [99].", encoding="utf-8")
    service = AuditService()
    service.provider.verify_citation = AsyncMock(side_effect=AssertionError("No usable metadata"))
    try:
        report = await service.audit_document(str(path))
        assert report.total_references == 0
        assert report.total_occurrences == 1
        assert report.results[0].evidence_status == "PARSE_INCOMPLETE"
        assert "UNRESOLVED_CITATION" in {d.code for d in report.parse_diagnostics}
    finally:
        await service.close()
