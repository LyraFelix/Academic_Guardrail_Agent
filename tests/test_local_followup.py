"""Exercise the real local lookup chain; model conclusions here are scripted fixtures."""

import json
from pathlib import Path

import pytest

from academic_guardrail.core.local_review import prepare_local_review, follow_up_review
from academic_guardrail.core.review_store import ReviewStore, content_digest
from tests.test_claim_review import judgment


PAPER = """Local Follow-up Study
Doe, Jane
2024
DOI: 10.1234/local-study

Abstract
The study investigates a treatment in adults.

Results
At six months, mortality was reduced by 25% compared with placebo.

Limitations
No pediatric participants were enrolled.

References
[1] Another paper reports 90% mortality reduction.
"""
CLAIM = "The treatment reduced mortality by 25% at six months."


@pytest.fixture
def local_setup(tmp_path):
    refs = tmp_path / "papers"
    refs.mkdir()
    source = refs / "study.txt"
    source.write_text(PAPER, encoding="utf-8")
    return refs, source, ReviewStore(tmp_path / "reviews")


async def start(local_setup, *, terms=None, scope="abstract"):
    refs, source, store = local_setup
    packet = await prepare_local_review(CLAIM, "10.1234/local-study", str(refs),
                                        initial_scope=scope, store=store)
    incomplete = judgment(packet, conclusion="NOT_ENOUGH_EVIDENCE", quotes=[],
                          missing_evidence=[{"kind": "RESULT", "claim_part": "mortality by 25%",
                                             "question": "What was the mortality change at six months?",
                                             "search_terms": terms or ["mortality", "six months"]}])
    saved = store.record(packet.packet_id, incomplete, content_digest(packet.model_dump(mode="json")))
    return packet, saved


@pytest.mark.asyncio
async def test_lookup_adds_body_and_neighbors_preserving_original(local_setup):
    _, source, store = local_setup
    original, before = await start(local_setup)
    frozen = store.load_packet(original.packet_id).model_dump(mode="json")
    assert "25%" not in " ".join(e.text for e in original.evidence)
    after = follow_up_review(before["review_id"], before["review_sha256"], store=store)
    assert after.claim == original.claim
    assert after.evidence[:len(original.evidence)] == original.evidence
    assert store.load_packet(original.packet_id).model_dump(mode="json") == frozen
    context = store.load_context(after.packet_id)
    assert context.round == 1 and context.retrieval_status == "ADDED"
    assert context.parent_review_id == before["review_id"]
    text = " ".join(e.text for e in after.evidence)
    assert "mortality was reduced by 25%" in text and "No pediatric participants" in text
    assert "90% mortality" not in text
    for unit in after.evidence:
        location = unit.location
        assert source.read_text(encoding="utf-8")[location.char_start:location.char_end] == unit.text
    quote = next(unit for unit in after.evidence if "mortality was reduced" in unit.text)
    recorded = store.record(after.packet_id, judgment(after, conclusion="SUPPORTED",
                            quotes=[{"evidence_id": quote.id, "quote": quote.text}]),
                            content_digest(after.model_dump(mode="json")))
    assert store.load_review(recorded["review_id"])["judgment"]["conclusion"] == "SUPPORTED"
    assert recorded["semantic_judgment_verified"] is False
    assert len(list(store.directory.glob("*.review.json"))) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["lookup", "record"])
async def test_changed_source_blocks_lookup_or_new_judgment(local_setup, stage):
    _, source, store = local_setup
    packet, before = await start(local_setup)
    if stage == "record":
        packet = follow_up_review(before["review_id"], before["review_sha256"], store=store)
    source.write_text(PAPER.replace("25%", "5%"), encoding="utf-8")
    with pytest.raises(ValueError, match="(?i)changed|current|source"):
        if stage == "lookup":
            follow_up_review(before["review_id"], before["review_sha256"], store=store)
        else:
            store.record(packet.packet_id, judgment(packet, conclusion="UNCERTAIN", quotes=[]),
                         content_digest(packet.model_dump(mode="json")))
    assert len(list(store.directory.glob("*.review.json"))) == 1


@pytest.mark.asyncio
async def test_only_one_lookup_per_root_and_no_second_round(local_setup):
    _, _, store = local_setup
    original, before = await start(local_setup)
    child = follow_up_review(before["review_id"], before["review_sha256"], store=store)
    with pytest.raises(ValueError, match="(?i)already|attempt"):
        follow_up_review(before["review_id"], before["review_sha256"], store=store)
    data = before["judgment"].copy()
    data["reviewed_evidence_ids"] = [unit.id for unit in child.evidence]
    from academic_guardrail.core.review_models import ClientJudgment
    second = store.record(child.packet_id, ClientJudgment.model_validate(data),
                          content_digest(child.model_dump(mode="json")))
    with pytest.raises(ValueError, match="(?i)round|once|follow-up"):
        follow_up_review(second["review_id"], second["review_sha256"], store=store)


@pytest.mark.asyncio
async def test_no_match_is_preserved_without_inventing_evidence(local_setup):
    _, _, store = local_setup
    original, before = await start(local_setup, terms=["unreported-endpoint-xyz"])
    child = follow_up_review(before["review_id"], before["review_sha256"], store=store)
    context = store.load_context(child.packet_id)
    assert child.evidence == original.evidence
    assert context.retrieval_status == "NO_MATCH" and context.added_evidence_ids == []


@pytest.mark.asyncio
async def test_full_text_packet_records_no_new_evidence(local_setup):
    _, _, store = local_setup
    original, before = await start(local_setup, scope="full_text")
    child = follow_up_review(before["review_id"], before["review_sha256"], store=store)
    assert child.evidence == original.evidence
    assert store.load_context(child.packet_id).retrieval_status == "NO_NEW_EVIDENCE"


@pytest.mark.asyncio
async def test_absent_abstract_stays_empty_until_lookup(local_setup):
    refs, source, store = local_setup
    source.write_text(PAPER.replace("Abstract\nThe study investigates a treatment in adults.\n\n", ""), encoding="utf-8")
    packet, before = await start(local_setup)
    assert not packet.evidence
    child = follow_up_review(before["review_id"], before["review_sha256"], store=store)
    assert child.evidence and "NO_EVIDENCE" not in child.blocking_reasons


@pytest.mark.asyncio
async def test_wrong_record_digest_and_missing_context_are_rejected(local_setup):
    _, _, store = local_setup
    packet, before = await start(local_setup)
    with pytest.raises(ValueError, match="(?i)digest|snapshot|checksum"):
        follow_up_review(before["review_id"], "0" * 64, store=store)
    store._path(packet.packet_id, "context").unlink()
    with pytest.raises(ValueError, match="(?i)context"):
        store.record(packet.packet_id, judgment(packet, conclusion="UNCERTAIN", quotes=[]),
                     content_digest(packet.model_dump(mode="json")))


@pytest.mark.asyncio
async def test_tampered_record_is_rejected(local_setup):
    _, _, store = local_setup
    _, before = await start(local_setup)
    path = store._path(before["review_id"], "review")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["judgment"]["rationale"] = "Changed after saving"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        store.load_review(before["review_id"])


@pytest.mark.asyncio
async def test_local_record_cannot_downgrade_to_legacy_by_removing_digest(local_setup):
    _, _, store = local_setup
    _, before = await start(local_setup)
    path = store._path(before["review_id"], "review")
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("review_sha256")
    data["judgment"]["rationale"] = "Untracked modification"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        store.load_review(before["review_id"])


@pytest.mark.asyncio
async def test_retracted_or_ambiguous_paper_cannot_start_local_workflow(local_setup):
    refs, source, store = local_setup
    source.write_text(PAPER.replace("10.1234/local-study", "10.1038/nature12968"), encoding="utf-8")
    with pytest.raises(ValueError, match="(?i)eligible|retracted|identity"):
        await prepare_local_review(CLAIM, "10.1038/nature12968", str(refs), store=store)
    source.write_text(PAPER, encoding="utf-8")
    (refs / "duplicate.txt").write_text(PAPER, encoding="utf-8")
    with pytest.raises(ValueError, match="(?i)eligible|ambiguous|identity"):
        await prepare_local_review(CLAIM, "10.1234/local-study", str(refs), store=store)


@pytest.mark.parametrize("gap", [
    {"claim_part": "invented requirement"}, {"search_terms": [" "]},
    {"search_terms": ["mortality", "MORTALITY"]}, {"search_terms": ["x" * 101]},
])
@pytest.mark.asyncio
async def test_invalid_gap_descriptions_are_not_saved(local_setup, gap):
    _, _, store = local_setup
    packet, before = await start(local_setup)
    data = before["judgment"].copy()
    data["missing_evidence"] = [{**data["missing_evidence"][0], **gap}]
    from academic_guardrail.core.review_models import ClientJudgment
    with pytest.raises(ValueError):
        store.record(packet.packet_id, ClientJudgment.model_validate(data),
                     content_digest(packet.model_dump(mode="json")))


def test_legacy_packet_serialization_is_unchanged(tmp_path):
    from tests.test_claim_review import packet
    value = packet()
    store = ReviewStore(tmp_path)
    raw = value.model_dump(mode="json")
    digest = store.save_packet(value)
    assert content_digest(store.load_packet(value.packet_id).model_dump(mode="json")) == digest
    assert set(raw) == {"schema_version", "packet_id", "claim", "reference_status", "reference",
                        "blocking_reasons", "evidence", "recommended_evidence_ids", "rule_assessment", "instructions"}
    assert store.load_context(value.packet_id) is None


@pytest.mark.asyncio
async def test_wrapped_citation_before_references_does_not_hide_results(local_setup):
    _, source, store = local_setup
    source.write_text(PAPER.replace("Results\n", "Background\n[38] Prior work was limited. This is still the body.\n\nResults\n"), encoding="utf-8")
    _, before = await start(local_setup)
    child = follow_up_review(before["review_id"], before["review_sha256"], store=store)
    assert any("mortality was reduced by 25%" in unit.text for unit in child.evidence)
    assert not any("90% mortality" in unit.text for unit in child.evidence)


@pytest.mark.asyncio
async def test_rechunked_long_abstract_does_not_count_as_new_evidence(local_setup):
    _, source, store = local_setup
    abstract = "The cohort " + "contains a repeated cohort observation " * 80 + "."
    source.write_text("Local Follow-up Study\n2024\nDOI: 10.1234/local-study\n\nAbstract\n" +
                      abstract + "\n\nReferences\n[1] Another cited paper.\n", encoding="utf-8")
    original, before = await start(local_setup, terms=["cohort"])
    assert len(original.evidence) == 1 and len(original.evidence[0].text) > 2400
    child = follow_up_review(before["review_id"], before["review_sha256"], store=store)
    assert child.evidence == original.evidence
    assert store.load_context(child.packet_id).retrieval_status == "NO_NEW_EVIDENCE"
