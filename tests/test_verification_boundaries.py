"""Safety contracts: reference identity, provenance and explicit offline mode."""
from unittest.mock import AsyncMock, patch

import pytest

from academic_guardrail.core.models import Citation, ContextClaim, PaperRecord
from academic_guardrail.core.ref_store import LocalRefStore
from academic_guardrail.core.service import AuditService


def citation():
    return Citation(id="cit_1", raw_text="Alice Smith. A randomized treatment trial. 2024.",
                    title="A randomized treatment trial", authors=["Alice Smith"], year=2024)


def claim():
    return ContextClaim(citation_id="cit_1", claim_sentence="Treatment improves survival.", surrounding_context="")


@pytest.mark.asyncio
async def test_ambiguous_retracted_candidate_is_not_a_confirmed_retraction():
    service = AuditService()
    service.provider.verify_citation = AsyncMock(return_value={
        "matched": True, "is_uncertain": True, "is_retracted": True,
        "title": "An ambiguous candidate", "confidence": 0.8,
    })
    try:
        result = await service.verify_single_item(citation(), claim())
        assert result.status == "UNVERIFIED"
        assert result.risk_level == "WARNING"
        assert result.retraction_status != "CONFIRMED"
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_suspected_retraction_remains_warning_even_with_matching_claim():
    service = AuditService()
    service.provider.verify_citation = AsyncMock(return_value={
        "matched": True, "title": citation().title, "abstract": claim().claim_sentence,
        "is_retracted": False, "retraction_status": "SUSPECTED",
        "sources": [{"source": "Crossref", "kind": "title_heuristic", "detail": "retraction keyword"}],
    })
    try:
        result = await service.verify_single_item(citation(), claim())
        assert result.risk_level == "WARNING"
        assert result.evidence_status == "RETRACTION_SUSPECTED"
        assert result.sources[0].kind == "title_heuristic"
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_sources_and_authors_survive_reference_verification():
    service = AuditService()
    service.provider.verify_citation = AsyncMock(return_value={
        "matched": True, "title": citation().title, "abstract": None,
        "retraction_status": "NO_RECORD", "sources": [{"source": "OpenAlex", "kind": "official_metadata", "identifier": "10.1234/a"}],
    })
    try:
        result = await service.verify_reference(citation())
        assert result.status == "VALID"
        assert result.verification_scope == "REFERENCE_METADATA"
        assert result.sources[0].identifier == "10.1234/a"
        assert service.provider.verify_citation.call_args.kwargs["authors"] == ["Alice Smith"]
        assert "未发现" in result.message
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_offline_service_never_initializes_online_provider_or_embedding_model(tmp_path):
    ref = tmp_path / "paper.txt"
    ref.write_text("A randomized treatment trial\nAlice Smith\n2024\nAbstract: Treatment improves survival.", encoding="utf-8")
    with patch("academic_guardrail.core.service.ChineseAcademicProvider", side_effect=AssertionError("online provider initialized")), \
         patch("academic_guardrail.core.semantic_matcher.SemanticMatcher._get_model", side_effect=AssertionError("model accessed")):
        service = AuditService(offline=True)
        try:
            result = await service.verify_single_item(citation(), claim(), LocalRefStore(str(tmp_path)))
            assert result.evidence_status == "LOCAL_MATCHED"
            assert result.verified_title == citation().title
            assert result.sources[0].kind == "local_file"
            assert result.retraction_status == "NOT_CHECKED"
            assert result.semantic_mode == "CORE"
        finally:
            await service.close()


@pytest.mark.asyncio
async def test_offline_known_doi_preserves_retraction_source():
    with patch("academic_guardrail.core.service.ChineseAcademicProvider", side_effect=AssertionError("network")):
        service = AuditService(offline=True)
        try:
            cit = Citation(id="r", raw_text="10.1038/nature12968", doi="10.1038/nature12968")
            result = await service.verify_reference(cit)
            assert result.status == "RETRACTED"
            assert result.retraction_status == "CONFIRMED"
            assert result.sources[0].kind == "offline_database"
        finally:
            await service.close()


@pytest.mark.asyncio
async def test_offline_unknown_doi_is_unverified_not_safe():
    service = AuditService(offline=True)
    try:
        result = await service.verify_reference(Citation(id="u", raw_text="10.1234/unknown", doi="10.1234/unknown"))
        assert result.status == "UNVERIFIED"
        assert result.retraction_status == "NO_RECORD"
        assert result.evidence_status == "OFFLINE_NO_MATCH"
    finally:
        await service.close()


def test_bibliography_mention_does_not_establish_local_identity():
    store = LocalRefStore()
    store.records = [PaperRecord(filename="other.txt", filepath="other.txt", title="Optical cavity control",
                                 abstract="Photons in cavities.", fulltext="References: A randomized treatment trial")]
    assert store.find_abstract_for_citation(citation().title, citation().raw_text) is None


def test_ambiguous_local_match_must_abstain():
    store = LocalRefStore()
    store.records = [PaperRecord(filename=f"{name}.txt", filepath=f"{name}.txt", title=citation().title,
                                 authors=[name], abstract="A study.") for name in ("Alice", "Bob")]
    assert store.find_abstract_for_citation(citation().title, "Unknown author") is None


@pytest.mark.asyncio
async def test_local_fallback_updates_evidence_status_and_keeps_online_failure(tmp_path):
    (tmp_path / "paper.txt").write_text("A randomized treatment trial\nAlice Smith\n2024\nAbstract: Treatment improves survival.", encoding="utf-8")
    service = AuditService()
    service.provider.verify_citation = AsyncMock(return_value={
        "matched": None, "title": "Wrong online metadata", "evidence_status": "PROVIDER_UNAVAILABLE", "failure_reason": "TIMEOUT",
    })
    try:
        result = await service.verify_single_item(citation(), claim(), LocalRefStore(str(tmp_path)))
        assert result.evidence_status == "LOCAL_MATCHED"
        assert result.verified_title == citation().title
        assert result.sources[-1].kind == "local_file"
        assert result.failure_reason == "TIMEOUT"
    finally:
        await service.close()


def test_identical_local_metadata_does_not_hide_conflicting_files():
    store = LocalRefStore()
    store.records = [
        PaperRecord(filename=f"{i}.txt", filepath=f"{i}.txt", title=citation().title, abstract=text)
        for i, text in enumerate(["Treatment improves survival.", "Treatment does not improve survival."])
    ]
    assert store.find_match(citation()) is None


def test_unmatched_retraction_flag_cannot_confirm_citation_identity():
    from academic_guardrail.core.reference_decision import decide_reference
    result = decide_reference(citation(), {"matched": False, "is_retracted": True})
    assert result.status == "UNVERIFIED"
    assert result.retraction_status == "NOT_CHECKED"


@pytest.mark.asyncio
async def test_retraction_reason_survives_text_and_markdown():
    from academic_guardrail.core.models import DocumentAuditReport
    from academic_guardrail.core.reporter import ReportGenerator
    from academic_guardrail.core.result_formatter import format_result
    service = AuditService(offline=True)
    try:
        result = await service.verify_reference(Citation(id="r", raw_text="10.1038/nature12968", doi="10.1038/nature12968"))
        assert result.retraction_info
        assert result.retraction_info in format_result(result)
        report = DocumentAuditReport(document_path="demo.txt", total_citations=1, passed_count=0,
                                     warning_count=0, danger_count=1, results=[result], offline=True)
        assert result.retraction_info in ReportGenerator().generate_markdown(report)
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_offline_corrupt_database_is_not_no_record(tmp_path, monkeypatch):
    db = tmp_path / "corrupt.db"
    db.write_text("This is not a SQLite database", encoding="utf-8")
    monkeypatch.setenv("RETRACTION_DB_PATH", str(db))
    service = AuditService(offline=True)
    try:
        result = await service.verify_reference(Citation(id="c", raw_text="10.1234/unknown", doi="10.1234/unknown"))
        assert result.status == "UNVERIFIED"
        assert result.retraction_status == "NOT_CHECKED"
        assert result.failure_reason == "OFFLINE_DB_UNAVAILABLE"
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_online_match_survives_local_database_failure(tmp_path, monkeypatch):
    db = tmp_path / "corrupt.db"
    db.write_text("invalid sqlite", encoding="utf-8")
    monkeypatch.setenv("RETRACTION_DB_PATH", str(db))
    service = AuditService()
    service.provider.openalex.get_by_doi = AsyncMock(return_value={
        "title": "A paper", "doi": "10.1234/a", "is_retracted": False})
    service.provider.crossref.get_by_doi = AsyncMock(return_value=None)
    try:
        result = await service.verify_reference(Citation(id="c", raw_text="10.1234/a", doi="10.1234/a"))
        assert result.status == "VALID"
        assert "OFFLINE_DB_UNAVAILABLE" in result.failure_reason
        assert any(s.kind == "offline_database" and s.is_retracted is None for s in result.sources)
    finally:
        await service.close()
