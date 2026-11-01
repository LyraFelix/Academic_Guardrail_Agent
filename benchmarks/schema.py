"""Small contracts separating visible inputs, hidden labels and predictions."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

State = Literal["TEXT_ALIGNED", "POTENTIAL_CONFLICT", "REVIEW_REQUIRED", "INSUFFICIENT_EVIDENCE"]
STATES = ("TEXT_ALIGNED", "POTENTIAL_CONFLICT", "REVIEW_REQUIRED", "INSUFFICIENT_EVIDENCE", "ERROR")
LABELS = ("SUPPORT", "CONTRADICT", "NEI")


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1)


class InputCase(Record):
    claim_id: str
    doc_id: str
    claim: str
    sentences: list[str]
    category: str | None = None


class GoldCase(Record):
    label: Literal["SUPPORT", "CONTRADICT", "NEI"] | None = None
    rationales: list[list[int]] = Field(default_factory=list)
    expected_state: State | None = None
    required_codes: list[str] = Field(default_factory=list)


class Prediction(Record):
    state: Literal["TEXT_ALIGNED", "POTENTIAL_CONFLICT", "REVIEW_REQUIRED", "INSUFFICIENT_EVIDENCE", "ERROR"]
    score: float | None = Field(default=None, ge=0, le=1)
    evidence_text: str = ""
    sentence_ids: list[int] = Field(default_factory=list)
    findings: list[dict] = Field(default_factory=list)
    engine: str | None = None
    elapsed_ms: float = Field(default=0.0, ge=0)
    error: str | None = None
