"""Checked local provenance sidecars keep the legacy packet v1 schema unchanged."""

from typing import Literal

from pydantic import Field

from academic_guardrail.core.models import Citation, EvidencePassage
from academic_guardrail.core.review_models import MissingEvidence, ReviewModel


class LocalSource(ReviewModel):
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    text_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    title: str
    doi: str | None = None


class LocalSearchResult(ReviewModel):
    """A lexical hit is a candidate passage, never proof that a gap is resolved."""
    query_terms: list[str]
    passages: list[EvidencePassage]
    matched_passages: int
    total_passages: int
    search_scope: str = "same_local_paper_body_excluding_bibliography"


class LocalReviewContext(ReviewModel):
    packet_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    packet_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source: LocalSource
    refs_root: str
    citation: Citation
    initial_scope: Literal["abstract", "full_text"]
    round: Literal[0, 1] = 0
    parent_review_id: str | None = None
    parent_review_sha256: str | None = None
    gap: MissingEvidence | None = None
    retrieval_status: Literal["NOT_REQUESTED", "ADDED", "NO_MATCH", "NO_NEW_EVIDENCE"] = "NOT_REQUESTED"
    query_terms: list[str] = Field(default_factory=list)
    added_evidence_ids: list[str] = Field(default_factory=list)
    matched_passages: int = 0
    total_passages: int = 0
    search_scope: str = "same_local_paper_body_excluding_bibliography"
