"""Contracts for client-model reasoning, separate from server verification."""

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from academic_guardrail.core.models import ClaimAssessment, SourceLocation


class ReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReviewEvidence(ReviewModel):
    id: str
    text: str = Field(min_length=1)
    source_kind: str
    location: SourceLocation | None = None


class ReviewPacket(ReviewModel):
    schema_version: Literal[1] = 1
    packet_id: str = Field(default_factory=lambda: uuid4().hex, pattern=r"^[a-f0-9]{32}$")
    claim: str = Field(min_length=1, max_length=12000)
    reference_status: str
    reference: dict | None = None
    blocking_reasons: list[str] = Field(default_factory=list)
    evidence: list[ReviewEvidence]
    recommended_evidence_ids: list[str]
    rule_assessment: ClaimAssessment
    instructions: str


class ReviewQuote(ReviewModel):
    evidence_id: str
    quote: str = Field(min_length=1, max_length=16000)


class ReviewChecks(ReviewModel):
    subject: str = Field(min_length=1, max_length=3000)
    relation: str = Field(min_length=1, max_length=3000)
    numbers: str = Field(min_length=1, max_length=3000)
    scope: str = Field(min_length=1, max_length=3000)
    counterevidence: str = Field(min_length=1, max_length=3000)


class SuggestedRevision(ReviewModel):
    """A source-linked drafting suggestion, not verification of the old claim."""
    text: str = Field(min_length=1, max_length=6000)
    evidence_ids: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=3000)


class ClaimFinding(ReviewModel):
    """The client's reading of one necessary claim part, never a server verdict."""
    claim_part: str = Field(min_length=1, max_length=3000, description="Exact substring of the original claim")
    relation: Literal["SUPPORTS", "CONTRADICTS", "NOT_ADDRESSED", "UNCLEAR"]
    evidence_ids: list[str] = Field(description="Distinct reviewed IDs, each with a matching exact quote in judgment.quotes")
    reason: str = Field(min_length=1, max_length=3000)


class MissingEvidence(ReviewModel):
    """The client's question for a bounded source lookup, not an inferred fact."""
    kind: Literal["ENTITY_MAPPING", "RESULT", "POPULATION", "COMPARATOR", "TIME", "OTHER"]
    claim_part: str = Field(min_length=1, max_length=3000)
    question: str = Field(min_length=1, max_length=1500)
    search_terms: list[str] = Field(min_length=1, max_length=6)


class ClientJudgment(ReviewModel):
    conclusion: Literal["SUPPORTED", "CONTRADICTED", "NOT_ENOUGH_EVIDENCE", "UNCERTAIN"]
    rationale: str = Field(min_length=1, max_length=6000)
    reviewed_evidence_ids: list[str]
    quotes: list[ReviewQuote]
    checks: ReviewChecks
    client_model: str = Field(default="unspecified", min_length=1, max_length=200)
    suggested_revision: SuggestedRevision | None = None
    findings: list[ClaimFinding] = Field(default_factory=list, max_length=16)
    missing_evidence: list[MissingEvidence] = Field(default_factory=list, max_length=4)
