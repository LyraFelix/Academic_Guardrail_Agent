"""One local-paper lookup between two client judgments, with immutable provenance."""

from pathlib import Path

from academic_guardrail.core.claim_review import build_review_packet
from academic_guardrail.core.followup_models import LocalReviewContext
from academic_guardrail.core.local_evidence import (
    ensure_current_source, search_local_evidence, snapshot_for_record,
)
from academic_guardrail.core.models import EvidencePassage, PaperRecord, VerificationResult, VerificationStatus
from academic_guardrail.core.ref_store import LocalRefStore
from academic_guardrail.core.result_formatter import citation_from_text
from academic_guardrail.core.review_models import ReviewPacket
from academic_guardrail.core.review_store import ReviewStore, content_digest
from academic_guardrail.core.service import AuditService


LOCAL_INSTRUCTIONS = """
This packet belongs to a local source snapshot. If information is missing, state
the exact claim_part, kind, question and 1-6 literal search_terms in missing_evidence.
Do not add unstated 'only', 'all', or exclusivity conditions to the claim. Describe
the missing link without inventing an alias or a result. First record your judgment.
For an initial NOT_ENOUGH_EVIDENCE or UNCERTAIN judgment, follow_up_local_claim can
search this same paper once using one recorded gap and the returned review_sha256.
Read all pages of the new packet, consider new AND old evidence, and record a new
judgment. A retrieval hit or changed conclusion is not proof of correctness.
Export explicit saved review IDs with generate_claim_review_report.
"""


async def prepare_local_review(claim: str, citation_str_or_doi: str, refs_dir: str,
                               initial_scope: str = "abstract", *, store: ReviewStore | None = None) -> ReviewPacket:
    """Match one local paper and freeze its real abstract or explicit full-text scope."""
    if initial_scope not in {"abstract", "full_text"}:
        raise ValueError("initial_scope must be abstract or full_text")
    root = Path(refs_dir).resolve()
    if not refs_dir.strip() or not root.is_dir():
        raise ValueError("Provide an existing local reference directory")
    citation = citation_from_text(citation_str_or_doi)
    references = LocalRefStore(str(root))
    service = AuditService(offline=True)
    try:
        reference = await service.verify_reference(citation, references)
    finally:
        await service.close()
    if reference.status != VerificationStatus.VALID:
        raise ValueError(f"Local reference is not identity-eligible: {reference.status.value}; {reference.message}")
    match = references.find_match(citation)
    if match is None:
        raise ValueError("Local reference identity is absent or ambiguous")
    paper = PaperRecord.model_validate(match)
    source = snapshot_for_record(paper, str(root))
    if initial_scope == "full_text":
        passages = paper.passages
    else:
        passages = ([EvidencePassage(text=paper.abstract, source_kind="LOCAL_ABSTRACT",
                                     location=paper.abstract_location)] if paper.abstract else [])
    packet = build_review_packet(claim, passages, reference)
    packet.reference["local_source_binding"] = source.model_dump(mode="json")
    packet.instructions = (packet.instructions + LOCAL_INSTRUCTIONS).strip()
    storage = store or ReviewStore()
    ensure_current_source(source)
    digest = storage.save_packet(packet)
    storage.save_context(LocalReviewContext(packet_id=packet.packet_id, packet_sha256=digest,
                         source=source, refs_root=str(root), citation=citation, initial_scope=initial_scope))
    return packet


def _evidence_key(unit):
    """The same physical sentence is not new merely because its source kind changed."""
    location = unit.location
    return (unit.text, location.file_path if location else None,
            location.char_start if location else None, location.char_end if location else None)


def _already_covered(unit, previous) -> bool:
    """Rechunking an already read long sentence does not add source coverage."""
    location = unit.location
    if location is None:
        return False
    for old in previous:
        span = old.location
        if (span is not None and span.file_path == location.file_path
                and span.char_start <= location.char_start <= location.char_end <= span.char_end):
            offset = location.char_start - span.char_start
            if old.text[offset:offset + len(unit.text)] == unit.text:
                return True
    return False


def follow_up_review(review_id: str, expected_review_sha256: str, gap_index: int = 0,
                     *, store: ReviewStore | None = None) -> ReviewPacket:
    storage = store or ReviewStore()
    before = storage.load_review(review_id)
    if before["review_sha256"] != expected_review_sha256:
        raise ValueError("Stored review differs from the requested review snapshot digest")
    parent = storage.load_packet(before["packet_id"])
    context = storage.load_context(parent.packet_id)
    if context is None:
        raise ValueError("Follow-up needs a packet from prepare_local_claim_review")
    if context.round != 0:
        raise ValueError("Only one follow-up round is supported")
    if before["judgment"]["conclusion"] not in {"NOT_ENOUGH_EVIDENCE", "UNCERTAIN"}:
        raise ValueError("Follow-up requires an unresolved initial judgment")
    gaps = before["judgment"].get("missing_evidence", [])
    if not isinstance(gap_index, int) or not 0 <= gap_index < len(gaps):
        raise ValueError("Select an existing recorded missing-evidence description")
    gap = gaps[gap_index]
    ensure_current_source(context.source)
    request = {"review_id": review_id, "review_sha256": expected_review_sha256, "gap_index": gap_index}
    storage.reserve_followup(parent.packet_id, request)
    try:
        search = search_local_evidence(context.source, gap["search_terms"])
        reference = VerificationResult.model_validate(parent.reference)
        retrieved = build_review_packet(parent.claim, search.passages, reference)
        seen = {_evidence_key(unit) for unit in parent.evidence}
        added = []
        for unit in retrieved.evidence:
            key = _evidence_key(unit)
            if key not in seen and not _already_covered(unit, parent.evidence):
                added.append(unit.model_copy(update={"id": f"e{len(parent.evidence) + len(added) + 1}"}))
                seen.add(key)
        combined = [*parent.evidence, *added]
        passages = [EvidencePassage(text=unit.text, source_kind=unit.source_kind, location=unit.location)
                    for unit in combined]
        child = build_review_packet(parent.claim, passages, reference)
        child.evidence = combined  # Preserve every original ID and exact source location.
        child.reference["local_source_binding"] = context.source.model_dump(mode="json")
        child.instructions = (child.instructions + LOCAL_INSTRUCTIONS +
                              "\nThis is the final lookup round; report any remaining gaps.").strip()
        # Recomputed hints refer to the same ordered evidence, never a new semantic answer.
        status = "ADDED" if added else "NO_NEW_EVIDENCE" if search.matched_passages else "NO_MATCH"
        ensure_current_source(context.source)
        digest = storage.save_packet(child)
        storage.save_context(LocalReviewContext(
            packet_id=child.packet_id, packet_sha256=digest, source=context.source,
            refs_root=context.refs_root, citation=context.citation, initial_scope=context.initial_scope,
            round=1, parent_review_id=review_id, parent_review_sha256=expected_review_sha256,
            gap=gap, retrieval_status=status, query_terms=search.query_terms,
            added_evidence_ids=[unit.id for unit in added], matched_passages=search.matched_passages,
            total_passages=search.total_passages, search_scope=search.search_scope,
        ))
    except Exception as exc:
        storage.save_followup_result(parent.packet_id, {**request, "status": "FAILED", "error": str(exc)})
        raise
    storage.save_followup_result(parent.packet_id, {**request, "status": status,
                                 "packet_id": child.packet_id, "packet_sha256": digest})
    return child
