"""A useful rule result must survive context without inventing a comparison."""

import pytest

from academic_guardrail.core.claim_checks.numbers import quantities
from academic_guardrail.providers.claim_eval import ClaimEvaluator


@pytest.mark.parametrize("claim,evidence,state", [
    ("Protein X, a membrane receptor, increases cell survival.",
     "Protein X, a membrane receptor, decreases cell survival.", "POTENTIAL_CONFLICT"),
    ("Integrin αvβ8 improves adhesion.", "Integrin αvβ8 improves adhesion.", "TEXT_ALIGNED"),
    ("Treatment improves survival.",
     "Treatment improves survival. Treatment may improve long-term survival in adults.", "TEXT_ALIGNED"),
    ("Treatment improves survival.",
     "Treatment improves survival. Treatment does not improve survival.", "REVIEW_REQUIRED"),
    ("Treatment improves survival.",
     "Treatment improves survival. There is no evidence that treatment improves survival.", "REVIEW_REQUIRED"),
    ("Treatment improves survival.",
     "Treatment improves survival. Treatment does not improve survival in all patients.", "REVIEW_REQUIRED"),
    ("Treatment increases systolic blood pressure.",
     "Treatment reduces diastolic blood pressure.", "REVIEW_REQUIRED"),
    ("Treatment improves survival in mice.",
     "Treatment reduces survival in humans.", "REVIEW_REQUIRED"),
])
def test_context_keeps_decisive_and_uncertain_cases_separate(claim, evidence, state):
    result = ClaimEvaluator(use_embeddings=False).assess(claim, evidence)
    assert result.state == state
    assert result.evidence_text in evidence


def test_primary_excerpt_preserves_complete_source_sentence():
    evidence = "Although the method did not improve accuracy, the method reduces training time."
    result = ClaimEvaluator(use_embeddings=False).assess("The method reduces training time.", evidence)
    assert result.state == "TEXT_ALIGNED"
    assert result.evidence_text == evidence


@pytest.mark.parametrize("text", ["αvβ8", "IL-2", "COVID-19", "H2A.Z", "Protein X2"])
def test_entity_identifiers_are_not_measurements(text):
    assert quantities(text) == []


def test_real_signed_quantities_still_parse():
    assert [str(item.value) for item in quantities("The change was -5 mg.")] == ["-0.005"]
