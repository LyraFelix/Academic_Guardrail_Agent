"""Identity must precede text retrieval; excerpts must round-trip to their source."""

from unittest.mock import AsyncMock

import pytest

from academic_guardrail.core.models import Citation, ContextClaim
from academic_guardrail.core.ref_store import LocalRefStore
from academic_guardrail.core.service import AuditService


TITLE = "A randomized clinical treatment trial"


def citation(doi=None):
    return Citation(id="cit_1", raw_text=TITLE, title=TITLE, authors=["Alice Smith"], year=2024, doi=doi)


def local_paper(tmp_path, name="paper.txt", doi="10.1234/trial", body="Treatment improves survival."):
    path = tmp_path / name
    path.write_text(f"{TITLE}\nAlice Smith\n2024\ndoi: {doi}\n\nAbstract: Short overview of trial design.\n\n1. Results\n{body}", encoding="utf-8")
    return path


def test_same_title_different_doi_is_rejected(tmp_path):
    local_paper(tmp_path, doi="10.1234/other")
    assert LocalRefStore(str(tmp_path)).find_match(citation("10.1234/trial")) is None


def test_doi_in_reference_list_is_not_paper_identity(tmp_path):
    path = tmp_path / "other.txt"
    path.write_text("An unrelated optical study\nBob Jones\n2023\n\nAbstract: Optical cavities.\n\nReferences\nSmith. A randomized clinical treatment trial. doi: 10.1234/trial", encoding="utf-8")
    store = LocalRefStore(str(tmp_path))
    assert store.records[0].doi is None
    assert store.find_match(citation("10.1234/trial")) is None
    assert not any("10.1234/trial" in p.text for p in store.records[0].passages)


def test_absent_abstract_stays_empty(tmp_path):
    (tmp_path / "paper.txt").write_text(f"{TITLE}\nAlice Smith\n2024\n\n1. Introduction\nSome body text.", encoding="utf-8")
    record = LocalRefStore(str(tmp_path)).records[0]
    assert record.abstract == ""
    assert record.passages


def test_unheaded_numbered_bibliography_doi_is_not_local_identity(tmp_path):
    path = tmp_path / "unrelated.txt"
    path.write_text("An unrelated optical study\nBob Jones\n2023\n\nOptical cavities are studied.\n\n[1] Smith. A clinical trial. doi:10.1234/target", encoding="utf-8")
    store = LocalRefStore(str(tmp_path))
    assert store.records[0].doi is None
    assert store.find_match(Citation(id="x", raw_text="10.1234/target", doi="10.1234/target")) is None
    assert not any("10.1234/target" in p.text for p in store.records[0].passages)


def test_blank_line_does_not_hide_labeled_frontmatter_doi(tmp_path):
    (tmp_path / "paper.txt").write_text(f"{TITLE}\nAlice Smith\n2024\n\ndoi:10.1234/other\n\nAbstract: Wrong paper secret text.", encoding="utf-8")
    store = LocalRefStore(str(tmp_path))
    assert store.records[0].doi == "10.1234/other"
    assert store.find_match(citation("10.1234/target")) is None


def test_known_target_doi_requires_local_doi_identity(tmp_path):
    (tmp_path / "paper.txt").write_text(f"{TITLE}\nAlice Smith\n2024\nAbstract: A same-title paper with unknown DOI.", encoding="utf-8")
    assert LocalRefStore(str(tmp_path)).find_match(citation("10.1234/target")) is None


@pytest.mark.asyncio
async def test_late_pdf_evidence_has_exact_file_page_and_offsets(tmp_path, make_text_pdf):
    path = make_text_pdf(tmp_path / "paper.pdf", [
        f"{TITLE}\nAlice Smith\n2024\nAbstract: Short overview of trial design.",
        "Methods\nWe studied a large cohort.",
        "Results\nTreatment improves survival in the trial population."])
    store = LocalRefStore(str(tmp_path))
    service = AuditService(offline=True)
    try:
        result = await service.verify_single_item(citation(), ContextClaim(citation_id="cit_1", claim_sentence="Treatment improves survival in the trial population.", surrounding_context=""), store)
        assert result.text_source == "LOCAL_FULLTEXT"
        assert result.retrieval_status == "AVAILABLE"
        assert result.evidence_location.page == 3
        assert result.evidence_location.file_path == str(path)
        location = result.evidence_location
        assert store.records[0].fulltext[location.char_start:location.char_end] == result.evidence_text
        assert "Short overview" in result.abstract_tldr
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_local_fulltext_is_used_even_when_online_has_abstract(tmp_path):
    local_paper(tmp_path)
    service = AuditService()
    service.provider.verify_citation = AsyncMock(return_value={"matched": True, "title": TITLE, "doi": "10.1234/trial", "abstract": "Short overview.", "confidence": 1.0})
    try:
        result = await service.verify_single_item(citation(), ContextClaim(citation_id="cit_1", claim_sentence="Treatment improves survival.", surrounding_context=""), LocalRefStore(str(tmp_path)))
        assert result.text_source == "LOCAL_FULLTEXT"
        assert result.evidence_location.file_path.endswith("paper.txt")
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_online_resolved_doi_prevents_wrong_local_abstract(tmp_path):
    local_paper(tmp_path, doi="10.1234/wrong", body="Wrong paper secret text.")
    service = AuditService()
    service.provider.verify_citation = AsyncMock(return_value={"matched": True, "title": TITLE, "doi": "10.1234/real", "confidence": 1.0})
    try:
        result = await service.verify_single_item(citation(), ContextClaim(citation_id="cit_1", claim_sentence="Wrong paper secret text.", surrounding_context=""), LocalRefStore(str(tmp_path)))
        assert result.evidence_text is None
        assert result.retrieval_status == "NO_TEXT"
        assert result.verified_doi == "10.1234/real"
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_ambiguous_local_files_are_visible_and_do_not_supply_text(tmp_path):
    local_paper(tmp_path, "first.txt", body="Treatment improves survival.")
    local_paper(tmp_path, "second.txt", body="Treatment worsens survival.")
    service = AuditService(offline=True)
    try:
        result = await service.verify_single_item(citation(), ContextClaim(citation_id="cit_1", claim_sentence="Treatment improves survival.", surrounding_context=""), LocalRefStore(str(tmp_path)))
        assert result.evidence_status == "AMBIGUOUS"
        assert result.retrieval_status == "AMBIGUOUS"
        assert result.evidence_text is None
        assert len(result.ambiguous_candidates) == 2
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_title_matched_local_doi_rechecks_offline_retraction(tmp_path):
    local_paper(tmp_path, doi="10.1038/nature12968")
    service = AuditService(offline=True)
    try:
        result = await service.verify_reference(citation(), LocalRefStore(str(tmp_path)))
        assert result.status == "RETRACTED"
        assert result.verified_doi == "10.1038/nature12968"
        assert any(s.kind == "offline_database" and s.is_retracted for s in result.sources)
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_new_local_doi_rechecks_database_in_online_mode_and_preserves_failure(tmp_path):
    local_paper(tmp_path, doi="10.1038/nature12968")
    service = AuditService()
    service.provider.verify_citation = AsyncMock(return_value={"matched": False, "evidence_status": "PROVIDER_UNAVAILABLE", "failure_reason": "TIMEOUT"})
    try:
        result = await service.verify_reference(citation(), LocalRefStore(str(tmp_path)))
        assert result.status == "RETRACTED"
        assert result.failure_reason == "TIMEOUT"
        assert any(s.kind == "offline_database" and s.is_retracted for s in result.sources)
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_multiple_frontmatter_dois_cannot_supply_text_for_known_other_doi(tmp_path):
    local_paper(tmp_path, doi="10.1234/other\nRelated DOI: 10.1234/third")
    store = LocalRefStore(str(tmp_path))
    service = AuditService(offline=True)
    try:
        result = await service.verify_single_item(citation("10.1234/target"), ContextClaim(citation_id="cit_1", claim_sentence="Treatment improves survival.", surrounding_context=""), store)
        assert result.status == "UNVERIFIED"
        assert result.evidence_text is None
        assert result.evidence_status != "LOCAL_MATCHED"
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_metadata_only_local_abstract_has_its_own_source_location(tmp_path):
    local_paper(tmp_path)
    store = LocalRefStore(str(tmp_path))
    service = AuditService(offline=True)
    try:
        result = await service.verify_reference(citation(), store)
        assert result.text_source == "LOCAL_ABSTRACT"
        assert result.evidence_location is not None
        location = result.evidence_location
        assert store.records[0].fulltext[location.char_start:location.char_end] == result.evidence_text
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_unrelated_passages_stay_insufficient_not_negative_evidence(tmp_path):
    local_paper(tmp_path, body="Quartz resonators oscillate.")
    service = AuditService(offline=True)
    try:
        result = await service.verify_single_item(citation(), ContextClaim(citation_id="cit_1", claim_sentence="Zebras migrate annually across grasslands.", surrounding_context=""), LocalRefStore(str(tmp_path)))
        assert result.retrieval_status == "NO_RELEVANT_PASSAGE"
        assert result.evidence_text is None
        assert result.evidence_location is None
        assert result.alignment_state == "INSUFFICIENT_EVIDENCE"
        assert "不表示断言为假" in result.message
    finally:
        await service.close()
