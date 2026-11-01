"""A declared opposite finding cannot silently become missing evidence."""

import pytest

from academic_guardrail.core.claim_review import validate_client_judgment
from tests.test_claim_review import judgment, packet as sample_packet


def packet():
    return sample_packet().model_copy(update={
        "claim": "Treatment increases mortality. The effect lasts ten years."})


def findings(relation="CONTRADICTS", ids=None):
    return [{"claim_part": "Treatment increases mortality.", "relation": relation,
             "evidence_ids": ["e1"] if ids is None else ids,
             "reason": "The supplied sentence reports a reduction instead."}]


@pytest.mark.parametrize("conclusion", ["NOT_ENOUGH_EVIDENCE", "SUPPORTED"])
def test_opposing_finding_cannot_be_recorded_as_missing_or_support(conclusion):
    value = packet()
    candidate = judgment(value, conclusion=conclusion, findings=findings())
    with pytest.raises(ValueError, match="finding"):
        validate_client_judgment(value, candidate)


def test_missing_detail_does_not_erase_a_declared_contradiction():
    value = packet()
    items = findings() + [{"claim_part": "The effect lasts ten years.",
                          "relation": "NOT_ADDRESSED", "evidence_ids": [],
                          "reason": "No long-term duration was reported."}]
    result = validate_client_judgment(value, judgment(value, conclusion="CONTRADICTED", findings=items))
    assert result["judgment"]["conclusion"] == "CONTRADICTED"
    assert result["findings_semantically_verified"] is False


@pytest.mark.parametrize("conclusion", ["SUPPORTED", "CONTRADICTED"])
def test_missing_result_alone_cannot_justify_a_decisive_conclusion(conclusion):
    value = packet()
    candidate = judgment(value, conclusion=conclusion, findings=findings("NOT_ADDRESSED", []))
    with pytest.raises(ValueError, match="finding"):
        validate_client_judgment(value, candidate)


@pytest.mark.parametrize("ids", [["e99"], ["e2"], ["e1", "e1"], []])
def test_positive_or_opposing_findings_need_distinct_quoted_ids(ids):
    value = packet()
    candidate = judgment(value, conclusion="CONTRADICTED", findings=findings(ids=ids))
    with pytest.raises(ValueError, match="finding"):
        validate_client_judgment(value, candidate)


def test_ambiguous_findings_can_be_uncertain_and_legacy_remains_valid():
    value = packet()
    result = validate_client_judgment(value, judgment(value, conclusion="UNCERTAIN", findings=findings("UNCLEAR", [])))
    assert result["judgment"]["conclusion"] == "UNCERTAIN"
    assert validate_client_judgment(value, judgment(value))["judgment"]["conclusion"] == "SUPPORTED"


def test_finding_cannot_silently_rewrite_the_claim():
    value = sample_packet()
    with pytest.raises(ValueError, match="original claim"):
        validate_client_judgment(value, judgment(value, conclusion="CONTRADICTED", findings=findings()))


def test_same_claim_part_cannot_be_both_supported_and_contradicted():
    value = packet()
    with pytest.raises(ValueError, match="one finding"):
        validate_client_judgment(value, judgment(value, conclusion="CONTRADICTED",
                                                findings=findings() + findings("SUPPORTS")))
