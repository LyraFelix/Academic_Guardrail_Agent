"""Give the client complete evidence; validate links without certifying reasoning."""

from academic_guardrail.core.claim_checks.text import sentence_units
from academic_guardrail.core.models import EvidencePassage, VerificationResult, VerificationStatus
from academic_guardrail.core.passages import locate_excerpt
from academic_guardrail.core.review_models import ClientJudgment, ReviewEvidence, ReviewPacket
from academic_guardrail.core.text_similarity import UniversalLexicalMatcher
from academic_guardrail.providers.claim_eval import ClaimEvaluator

from academic_guardrail.core.review_instructions import REVIEW_INSTRUCTIONS


def build_review_packet(claim: str, passages: list[EvidencePassage],
                        reference: VerificationResult | None = None) -> ReviewPacket:
    """Freeze only identity-eligible sources; preserve each full sentence's span."""
    blocking = []
    if reference and reference.status != VerificationStatus.VALID:
        blocking.append(f"REFERENCE_{reference.status.value}")
        passages = []
    if sum(len(p.text) for p in passages) > 240_000:
        raise ValueError("Reference text exceeds 240000 characters; provide a bounded source section")
    evidence = []
    for passage in passages:
        for unit in sentence_units(passage.text, split_semicolons=False):
            if len(unit.text) > 16_000:
                raise ValueError("One source sentence exceeds 16000 characters; inspect text extraction")
            evidence.append(ReviewEvidence(id=f"e{len(evidence) + 1}", text=unit.text,
                                          source_kind=passage.source_kind,
                                          location=locate_excerpt(passage, unit.text, offset=unit.start)))
    if not evidence:
        blocking.append("NO_EVIDENCE")
    ranked = sorted(evidence, key=lambda item: UniversalLexicalMatcher.compute_lexical_similarity(claim, item.text), reverse=True)
    return ReviewPacket(
        claim=claim, reference_status=reference.status.value if reference else "PROVIDED_TEXT_NOT_IDENTITY_VERIFIED",
        reference=reference.model_dump(mode="json") if reference else None,
        blocking_reasons=blocking, evidence=evidence,
        recommended_evidence_ids=[item.id for item in ranked[:5]],
        rule_assessment=ClaimEvaluator(use_embeddings=False).assess_passages(claim, passages),
        instructions=REVIEW_INSTRUCTIONS,
    )


def evidence_page(packet: ReviewPacket, offset: int = 0, limit: int = 24) -> dict:
    if offset < 0 or offset > len(packet.evidence) or not 1 <= limit <= 50:
        raise ValueError("Invalid evidence page; offset must be in range and limit between 1 and 50")
    selected, characters = [], 0
    for item in packet.evidence[offset:offset + limit]:
        if selected and characters + len(item.text) > 24_000:
            break
        selected.append(item.model_dump(mode="json"))
        characters += len(item.text)
    following = offset + len(selected)
    return {"packet_id": packet.packet_id, "total_evidence": len(packet.evidence),
            "offset": offset, "evidence": selected,
            "next_offset": following if following < len(packet.evidence) else None}


def validate_client_judgment(packet: ReviewPacket, judgment: ClientJudgment) -> dict:
    """Check the declared coverage and literal quotes, not semantic correctness."""
    indexed = {item.id: item for item in packet.evidence}
    reviewed = set(judgment.reviewed_evidence_ids)
    if len(reviewed) != len(judgment.reviewed_evidence_ids) or reviewed - set(indexed):
        raise ValueError("Duplicate or unknown reviewed evidence IDs")
    if judgment.conclusion != "UNCERTAIN" and reviewed != set(indexed):
        raise ValueError("Resolved judgments must declare every packet evidence ID as considered; read remaining pages first")
    decisive = judgment.conclusion in {"SUPPORTED", "CONTRADICTED"}
    if decisive and (packet.blocking_reasons or not judgment.quotes):
        raise ValueError("Support/contradiction requires available identity-eligible evidence and at least one quote")
    quotes = []
    for quote in judgment.quotes:
        item = indexed.get(quote.evidence_id)
        if item is None or item.id not in reviewed:
            raise ValueError("Quote refers to unknown or unreviewed evidence")
        if quote.quote not in item.text:
            raise ValueError(f"Quote is not an exact substring of {item.id}")
        passage = EvidencePassage(text=item.text, source_kind=item.source_kind, location=item.location)
        location = locate_excerpt(passage, quote.quote)
        quotes.append({**quote.model_dump(), "source_kind": item.source_kind,
                       "location": location.model_dump() if location else None})
    _validate_findings(packet, judgment)
    revision = judgment.suggested_revision
    if revision is not None:
        ids = set(revision.evidence_ids)
        quoted = {quote.evidence_id for quote in judgment.quotes}
        if packet.blocking_reasons or reviewed != set(indexed):
            raise ValueError("A revision needs eligible evidence and complete declared review")
        if len(ids) != len(revision.evidence_ids) or not ids <= quoted:
            raise ValueError("Revision evidence IDs must be distinct, reviewed and quoted")
    return {"packet_id": packet.packet_id, "judgment_origin": "CLIENT_MODEL",
            "judgment": judgment.model_dump(mode="json"), "quotes": quotes,
            "validation_status": "EVIDENCE_LINKS_VALID", "semantic_judgment_verified": False,
            "suggested_revision_semantically_verified": False,
            "findings_semantically_verified": False,
            "coverage_basis": "client_declared_evidence_ids_not_observed_cognition",
            "reference_status": packet.reference_status,
            "scope": "provided_source_text_only", "blocking_reasons": packet.blocking_reasons}


def _validate_findings(packet: ReviewPacket, judgment: ClientJudgment) -> None:
    """Reject inconsistent declarations; do not infer relations from the text."""
    if not judgment.findings:  # Older clients can still submit the original schema.
        return
    parts = [finding.claim_part for finding in judgment.findings]
    if len(set(parts)) != len(parts):
        raise ValueError("Use one finding per claim_part; represent conflicting observations as UNCLEAR")
    quoted = {quote.evidence_id for quote in judgment.quotes}
    for finding in judgment.findings:
        if finding.claim_part not in packet.claim:
            raise ValueError("Each finding claim_part must be an exact substring of the original claim")
        ids = set(finding.evidence_ids)
        if len(ids) != len(finding.evidence_ids) or not ids <= quoted:
            raise ValueError("Each finding needs distinct, reviewed and quoted evidence IDs")
        if finding.relation in {"SUPPORTS", "CONTRADICTS"} and not ids:
            raise ValueError("A positive or opposing finding needs quoted evidence")
    relations = {finding.relation for finding in judgment.findings}
    conclusion = judgment.conclusion
    if conclusion == "UNCERTAIN":
        return  # Ambiguity/conflict can remain unresolved; no forced label.
    if conclusion == "CONTRADICTED":
        valid = "CONTRADICTS" in relations
    elif conclusion == "SUPPORTED":
        valid = relations == {"SUPPORTS"}
    else:
        valid = "NOT_ADDRESSED" in relations and "CONTRADICTS" not in relations
    if not valid:
        raise ValueError("Conclusion conflicts with the declared claim findings; review the evidence and findings")
