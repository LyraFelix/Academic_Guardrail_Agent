"""Small, explicit behavior contracts; fixtures never enter the production checker."""

import json
from pathlib import Path

import pytest

from academic_guardrail.providers.claim_eval import ClaimEvaluator

CASES = json.loads((Path(__file__).parent / "fixtures/semantic_cases.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_semantic_counterexample(case):
    evaluator = ClaimEvaluator(use_embeddings=False)
    # Named results keep retrieval similarity, review state and reasons separate.
    result = evaluator.assess(case["claim"], case["evidence"])
    assert result.state == case["expected_state"]
    assert set(case["required_codes"]) <= {finding.code for finding in result.findings}
    assert 0 <= result.similarity_score <= 1
    assert result.state not in {"SUPPORTED", "CONTRADICTED"}
    for finding in result.findings:
        assert finding.evidence_text in case["evidence"]
        assert finding.claim_text in case["claim"]


def test_original_numeric_and_negation_failures_no_longer_claim_support():
    evaluator = ClaimEvaluator(use_embeddings=False)
    for claim, evidence in [
        ("The treatment reduced mortality by 90 percent.", "The treatment reduced mortality by 10 percent."),
        ("Treatment improves survival.", "Treatment doesn't improve survival."),
    ]:
        result = evaluator.evaluate_alignment(claim, evidence)
        assert result[3] == "POTENTIAL_CONFLICT"


def test_decimal_and_abbreviation_sentence_spans():
    evaluator = ClaimEvaluator(use_embeddings=False)
    sentences = evaluator.split_sentences("The dose was 3.5 mg. The rate was 10.2%.")
    assert len(sentences) == 2
    assert "3.5 mg" in sentences[0]
    assert "10.2%" in sentences[1]
