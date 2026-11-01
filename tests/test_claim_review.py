"""Client judgments stay distinct from mechanical quote/provenance validation."""

import json

import pytest

from academic_guardrail.core.claim_review import build_review_packet, evidence_page, validate_client_judgment
from academic_guardrail.core.review_models import ClientJudgment
from academic_guardrail.core.review_store import ReviewStore
from academic_guardrail.core.models import EvidencePassage, SourceLocation


def packet():
    text = "Treatment reduces mortality. The effect was measured in adults."
    passage = EvidencePassage(text=text, source_kind="LOCAL_FULLTEXT", location=SourceLocation(
        file_path="study.txt", page=2, line=3, char_start=100, char_end=100 + len(text)))
    return build_review_packet("Treatment reduces mortality in adults.", [passage])


def judgment(value, **updates):
    data = {
        "conclusion": "SUPPORTED", "rationale": "The provided text reports the effect in adults.",
        "reviewed_evidence_ids": [item.id for item in value.evidence],
        "quotes": [{"evidence_id": value.evidence[0].id, "quote": "Treatment reduces mortality."}],
        "checks": {"subject": "Same treatment.", "relation": "Both describe reduction.",
                   "numbers": "No numerical comparison.", "scope": "Adults only.",
                   "counterevidence": "No opposing statement in the provided text."},
        "client_model": "test fixture, not a live model",
    }
    data.update(updates)
    return ClientJudgment.model_validate(data)


def test_packet_keeps_complete_evidence_and_source_coordinates():
    value = packet()
    assert len(value.evidence) == 2
    assert value.evidence[0].text == "Treatment reduces mortality."
    assert value.evidence[0].location.char_start == 100
    assert value.evidence[1].location.char_start == 129
    assert value.reference_status == "PROVIDED_TEXT_NOT_IDENTITY_VERIFIED"
    assert "untrusted" in value.instructions.lower()


def test_pagination_never_silently_discards_sentences():
    value = packet()
    first = evidence_page(value, offset=0, limit=1)
    second = evidence_page(value, offset=first["next_offset"], limit=1)
    assert first["total_evidence"] == second["total_evidence"] == 2
    assert second["next_offset"] is None
    assert [first["evidence"][0]["id"], second["evidence"][0]["id"]] == [item.id for item in value.evidence]


def test_valid_quotes_do_not_certify_model_reasoning():
    value = packet()
    result = validate_client_judgment(value, judgment(value))
    assert result["validation_status"] == "EVIDENCE_LINKS_VALID"
    assert result["semantic_judgment_verified"] is False
    assert result["judgment_origin"] == "CLIENT_MODEL"
    assert result["quotes"][0]["location"]["char_start"] == 100


@pytest.mark.parametrize("problem", ["invented_quote", "unknown_id", "partial_read", "duplicate_read", "no_quote", "quote_not_read"])
def test_invalid_submissions_are_rejected(problem):
    value = packet()
    updates = {
        "invented_quote": {"quotes": [{"evidence_id": "e1", "quote": "Treatment increases mortality."}]},
        "unknown_id": {"quotes": [{"evidence_id": "e99", "quote": "Treatment reduces mortality."}]},
        "partial_read": {"reviewed_evidence_ids": ["e1"]},
        "duplicate_read": {"reviewed_evidence_ids": ["e1", "e1", "e2"]},
        "no_quote": {"quotes": []},
        "quote_not_read": {"conclusion": "UNCERTAIN", "reviewed_evidence_ids": ["e2"]},
    }[problem]
    with pytest.raises(ValueError):
        validate_client_judgment(value, judgment(value, **updates))


def test_empty_evidence_cannot_support_or_contradict():
    value = build_review_packet("A claim.", [])
    data = judgment(packet()).model_dump()
    data.update(quotes=[], reviewed_evidence_ids=[])
    with pytest.raises(ValueError):
        validate_client_judgment(value, ClientJudgment.model_validate(data))
    data["conclusion"] = "NOT_ENOUGH_EVIDENCE"
    assert validate_client_judgment(value, ClientJudgment.model_validate(data))["judgment"]["conclusion"] == "NOT_ENOUGH_EVIDENCE"


def test_store_preserves_snapshot_and_each_review(tmp_path):
    store = ReviewStore(tmp_path)
    value = packet()
    store.save_packet(value)
    assert store.load_packet(value.packet_id) == value
    first = store.record(value.packet_id, judgment(value))
    second = store.record(value.packet_id, judgment(value))
    assert first["review_id"] != second["review_id"]
    assert len(list(tmp_path.glob("*.review.json"))) == 2
    with pytest.raises(FileExistsError):
        store.save_packet(value)


def test_changed_packet_or_path_traversal_is_rejected(tmp_path):
    store, value = ReviewStore(tmp_path), packet()
    store.save_packet(value)
    path = tmp_path / f"{value.packet_id}.packet.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["packet"]["claim"] = "Changed claim."
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        store.load_packet(value.packet_id)
    with pytest.raises(ValueError):
        store.load_packet("../outside")


def test_missing_reasoning_dimensions_are_rejected():
    data = judgment(packet()).model_dump()
    del data["checks"]["counterevidence"]
    with pytest.raises(ValueError):
        ClientJudgment.model_validate(data)


def test_repeated_sentences_keep_their_distinct_locations():
    text = "Treatment reduces mortality. Treatment reduces mortality."
    passage = EvidencePassage(text=text, source_kind="LOCAL_FULLTEXT", location=SourceLocation(
        file_path="study.txt", page=1, line=1, char_start=100, char_end=100 + len(text)))
    value = build_review_packet("Treatment reduces mortality.", [passage])
    assert [item.location.char_start for item in value.evidence] == [100, 129]


def test_retracted_reference_cannot_be_laundered_into_support():
    from academic_guardrail.core.models import Citation, RiskLevel, VerificationResult, VerificationStatus
    reference = VerificationResult(citation=Citation(id="1", raw_text="Study"),
                                   status=VerificationStatus.RETRACTED, risk_level=RiskLevel.DANGER,
                                   message="Confirmed same-identity retraction")
    value = build_review_packet("Treatment reduces mortality.",
                                [EvidencePassage(text="Treatment reduces mortality.", source_kind="LOCAL_FULLTEXT")], reference)
    assert not value.evidence
    assert "REFERENCE_RETRACTED" in value.blocking_reasons
    with pytest.raises(ValueError):
        validate_client_judgment(value, judgment(packet(), reviewed_evidence_ids=[], quotes=[]))


@pytest.mark.asyncio
async def test_mcp_client_workflow_uses_stored_packet(monkeypatch, tmp_path):
    from academic_guardrail import mcp_server
    monkeypatch.setenv("ACADEMIC_GUARDRAIL_REVIEW_DIR", str(tmp_path / "reviews"))
    result = await mcp_server.prepare_claim_review("Treatment reduces mortality.",
                                                  reference_text="Treatment reduces mortality.", offline=True)
    stored = ReviewStore(tmp_path / "reviews").load_packet(result["packet_id"])
    page = await mcp_server.read_claim_evidence(result["packet_id"])
    assert page["evidence"][0]["text"] == "Treatment reduces mortality."
    saved = await mcp_server.record_claim_review(result["packet_id"], judgment(stored))
    assert saved["judgment_origin"] == "CLIENT_MODEL"
    assert saved["semantic_judgment_verified"] is False


@pytest.mark.asyncio
async def test_mcp_rejects_ambiguous_input_sources():
    from academic_guardrail.mcp_server import prepare_claim_review
    with pytest.raises(ValueError):
        await prepare_claim_review("Claim", reference_text="Text", citation_str_or_doi="A paper")


@pytest.mark.asyncio
async def test_mcp_local_reference_keeps_identity_and_source(tmp_path):
    from academic_guardrail.mcp_server import prepare_claim_review
    ref_dir = tmp_path / "references"
    ref_dir.mkdir()
    (ref_dir / "study.txt").write_text("Title: Synthetic Treatment Study\nYear: 2024\nAbstract: Treatment reduces mortality.\n", encoding="utf-8")
    result = await prepare_claim_review("Treatment reduces mortality.", citation_str_or_doi="Synthetic Treatment Study",
                                       refs_dir=str(ref_dir), offline=True)
    assert result["reference_status"] == "VALID"
    assert result["evidence"]
    assert result["evidence"][0]["location"]["file_path"].endswith("study.txt")
