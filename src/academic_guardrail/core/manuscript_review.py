"""Prepare one local evidence packet for each citation occurrence in a fixed draft."""

import hashlib
from pathlib import Path
from uuid import uuid4

from academic_guardrail.core.local_evidence import snapshot_for_record
from academic_guardrail.core.local_review import save_initial_packet
from academic_guardrail.core.models import VerificationStatus
from academic_guardrail.core.ref_store import LocalRefStore
from academic_guardrail.core.review_instructions import REVIEW_INSTRUCTIONS
from academic_guardrail.core.review_store import ReviewStore, content_digest
from academic_guardrail.core.service import AuditService


MANUSCRIPT_STEPS = """For each PENDING occurrence, read its own packet with read_claim_evidence
starting at offset 0. Follow next_offset until null and check the packet_sha256 on every page.
Use record_claim_review with that packet_id, digest and your ClientJudgment. Keep repeated citations
separate. If an initial judgment needs more evidence from this same paper, record a specific
missing_evidence gap, call follow_up_local_claim once, read the extended packet and record it.
Preserve BLOCKED rows and parsing diagnostics. Finally call generate_manuscript_review_report
with manuscript_id and the requested new .html output_path. It finds all saved reviews for this
manuscript, includes pending and blocked rows, and shows competing reviews when present."""


def _blocked_reason(reference):
    if reference.citation.parse_status != "PARSED":
        return f"{reference.citation.parse_status} bibliography entry. {reference.message}"
    if reference.status != VerificationStatus.VALID:
        return f"{reference.evidence_status.value if reference.evidence_status else reference.status.value}. {reference.message}"
    if reference.retrieval_status == "AMBIGUOUS":
        return "AMBIGUOUS local reference. Supply one identity-matched paper."
    return "MISSING_LOCAL_SOURCE. Supply an identity-matched paper in refs_dir."


async def prepare_manuscript(file_path: str, refs_dir: str, initial_scope: str, service: AuditService,
                             store: ReviewStore) -> dict:
    """Hash the bytes actually parsed, index the library once and publish an immutable review queue."""
    document = Path(file_path).expanduser().resolve()
    root = Path(refs_dir).expanduser().resolve()
    if document.suffix.lower() not in {".md", ".docx"}:
        raise ValueError("Provide a local .md or .docx manuscript")
    if not refs_dir.strip() or not root.is_dir():
        raise ValueError("Provide an existing local reference directory")
    if initial_scope not in {"abstract", "full_text"}:
        raise ValueError("initial_scope must be full_text or abstract")

    raw = document.read_bytes()
    manuscript = {"manuscript_id": uuid4().hex, "manuscript_sha256": hashlib.sha256(raw).hexdigest(),
                  "document_path": str(document)}
    parsed = service.parser.parse(str(document), source_bytes=raw)
    references = LocalRefStore(str(root), excluded_paths=[document])
    report, prepared = await service.audit_parsed_document(str(document), parsed, references)
    papers = {paper.filepath: paper for paper in references.records}
    sources = {}  # Each matched file has one source snapshot, shared by repeated occurrences.
    packets, occurrences = {}, []

    for claim in parsed.occurrences:
        matched = prepared[claim.citation_id]  # Identity/retraction, before heuristic alignment.
        reference = matched.result
        paper = papers.get(matched.local_path)
        row = {"occurrence_id": claim.occurrence_id, "citation_id": claim.citation_id,
               "claim": claim.claim_sentence, "marker": claim.marker,
               "location": claim.location.model_dump(mode="json"), "reference_status": reference.status.value,
               "citation_text": reference.citation.raw_text, "title": reference.verified_title or reference.citation.title,
               "doi": reference.verified_doi or reference.citation.doi,
               "retraction_status": reference.retraction_status.value, "state": "BLOCKED",
               "reason": _blocked_reason(reference), "source_path": None,
               "packet_id": None, "packet_sha256": None, "total_evidence": 0}
        if paper is not None and reference.status == VerificationStatus.VALID:
            row["source_path"] = paper.filepath
            try:
                if paper.filepath not in sources:
                    sources[paper.filepath] = snapshot_for_record(paper, str(root))
                if not paper.passages and (initial_scope == "full_text" or not paper.abstract):
                    raise ValueError("NO_SOURCE_TEXT. The matched file contains no usable article passages.")
                binding = {**manuscript, "citation_id": claim.citation_id, "occurrence_id": claim.occurrence_id}
                packet = save_initial_packet(store, claim.claim_sentence, reference, paper,
                                             sources[paper.filepath], str(root), initial_scope,
                                             manuscript_binding=binding)
            except ValueError as exc:
                # A too-long paper, stale file or unsupported extraction blocks this occurrence only.
                row["reason"] = str(exc)
            else:
                row.update(state="PENDING", reason="" if packet.evidence else "NO_INITIAL_EVIDENCE. Record the gap before a local follow-up.",
                           packet_id=packet.packet_id, packet_sha256=content_digest(packet.model_dump(mode="json")),
                           total_evidence=len(packet.evidence))
        packets[claim.occurrence_id] = row
        occurrences.append(row)

    settings = {"refs_dir": str(root), "initial_scope": initial_scope, "offline": service.offline}
    store.save_manuscript({**manuscript, **settings, "report": report.model_dump(mode="json"),
                           "packets": packets, "sources": {path: source.model_dump(mode="json")
                                                          for path, source in sources.items()}})
    return {**manuscript, **settings, "total_occurrences": len(occurrences), "occurrences": occurrences,
            "suggested_output_path": str(document.with_name(document.stem + "_manuscript_review.html")),
            "total_references": report.total_references,
            "parse_diagnostics": [item.model_dump(mode="json") for item in report.parse_diagnostics],
            "instructions": MANUSCRIPT_STEPS + "\n" + REVIEW_INSTRUCTIONS}
