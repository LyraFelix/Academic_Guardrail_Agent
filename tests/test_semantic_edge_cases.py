"""Adversarial regressions: abstention is preferable to an invented comparison."""

import pytest
from academic_guardrail.providers.claim_eval import ClaimEvaluator


@pytest.mark.parametrize("claim,evidence,state,code", [
    ("Exercise causes improved survival.", "Exercise does not cause improved survival.", "POTENTIAL_CONFLICT", "NEGATION_DIFFERENCE"),
    ("The dose was 5 mg.", "The dose was not 5 mg.", "POTENTIAL_CONFLICT", "NEGATION_DIFFERENCE"),
    ("The dose was .5 mg.", "The dose was .6 mg.", "POTENTIAL_CONFLICT", "NUMBER_MISMATCH"),
    ("Drug A improves survival.", "Drug B improves survival.", "INSUFFICIENT_EVIDENCE", "TARGET_MISMATCH"),
    ("The method improves accuracy and reliability.", "The method improves accuracy.", "REVIEW_REQUIRED", "COMPOUND_CLAIM"),
    ("Exercise causes improved survival.", "Improved survival causes exercise.", "INSUFFICIENT_EVIDENCE", "TARGET_MISMATCH"),
    ("Treatment improves survival.", "In mice, treatment improves survival.", "REVIEW_REQUIRED", "SCOPE_OMITTED"),
    ("Treatment improves survival.", "Treatment improves survival in diabetic patients.", "REVIEW_REQUIRED", "SCOPE_OMITTED"),
    ("Treatment improves survival in older adults.", "Treatment improves survival in younger adults.", "REVIEW_REQUIRED", "POPULATION_CHANGED"),
    ("Treatment improves survival.", "Does treatment improve survival?", "REVIEW_REQUIRED", "NON_ASSERTIVE_TEXT"),
    ("Treatment improves survival.", "We hypothesized that treatment improves survival.", "REVIEW_REQUIRED", "NON_ASSERTIVE_TEXT"),
    ("Treatment reduces mortality by 5 units.", "Treatment reduces mortality by 6 copies.", "REVIEW_REQUIRED", "UNKNOWN_UNIT"),
    ("The concentration was 5 mg/kg.", "The concentration was 6 mg/ml.", "REVIEW_REQUIRED", "COMPLEX_QUANTITY"),
    ("The rate was less than 10%.", "The rate was at most 10%.", "REVIEW_REQUIRED", "NUMERIC_QUALIFIER_CHANGED"),
    ("The rate was >10%.", "The rate was 10%.", "REVIEW_REQUIRED", "NUMERIC_QUALIFIER_CHANGED"),
    ("Treatment reduces mortality by 10%.", "Treatment does not reduce mortality by 20%.", "REVIEW_REQUIRED", "NEGATED_QUANTITY"),
    ("Treatment increases systolic blood pressure.", "Treatment reduces diastolic blood pressure.", "REVIEW_REQUIRED", "COMPARISON_UNCERTAIN"),
    ("Treatment improves survival in mice.", "Treatment reduces survival in humans.", "REVIEW_REQUIRED", "POPULATION_CHANGED"),
    ("Treatment improves survival.", "Treatment improves survival only when administered early.", "REVIEW_REQUIRED", "SCOPE_OMITTED"),
    ("The rate was 0.5%.", "The rate was .5 percent.", "TEXT_ALIGNED", None),
    ("No treatment improves survival.", "No treatment improves survival.", "TEXT_ALIGNED", None),
    ("Treatment improves survival.", "Treatment improves survival, only in mice.", "REVIEW_REQUIRED", "SCOPE_OMITTED"),
    ("Treatment improves survival.", "If treatment is administered early, treatment improves survival.", "REVIEW_REQUIRED", "NON_ASSERTIVE_TEXT"),
    ("Treatment causes mortality.", "Treatment reduces mortality.", "REVIEW_REQUIRED", "COMPARISON_UNCERTAIN"),
    ("Exercise leads to improved survival.", "Exercise does not lead to improved survival.", "POTENTIAL_CONFLICT", "NEGATION_DIFFERENCE"),
    ("Treatment improves survival.", "After 12 weeks, treatment improves survival.", "REVIEW_REQUIRED", "TIME_SCOPE_CHANGED"),
    ("Treatment improves survival.", "At 12 weeks, treatment improves survival.", "REVIEW_REQUIRED", "TIME_SCOPE_CHANGED"),
    ("Treatment improves survival.", "Treatment improves survival, after 12 weeks.", "REVIEW_REQUIRED", "TIME_SCOPE_CHANGED"),
    ("药物提高生存率。", "12周后，药物提高生存率。", "REVIEW_REQUIRED", "TIME_SCOPE_CHANGED"),
    ("Trial therapy reduced mortality by 90% [1].", "Results\nTrial therapy reduced mortality by 10%.", "POTENTIAL_CONFLICT", "NUMBER_MISMATCH"),
    ("Trial therapy improves pain relief [1].", "Trial therapy does not improve pain relief.", "POTENTIAL_CONFLICT", "NEGATION_DIFFERENCE"),
])
def test_bounded_semantic_comparison(claim, evidence, state, code):
    assessment = ClaimEvaluator(use_embeddings=False).assess(claim, evidence)
    assert assessment.state == state
    if code:
        assert code in {f.code for f in assessment.findings}
    for item in assessment.findings:
        assert item.claim_text in claim
        assert item.evidence_text in evidence
