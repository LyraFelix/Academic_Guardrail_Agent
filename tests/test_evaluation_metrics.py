"""Hand-counted metrics prevent omission, abstention and undefined-rate mistakes."""

import pytest

from benchmarks.metrics import score_predictions
from benchmarks.schema import GoldCase, InputCase, Prediction


def sample_data():
    labels = ["CONTRADICT", "SUPPORT", "CONTRADICT", "NEI", "SUPPORT"]
    states = ["POTENTIAL_CONFLICT", "POTENTIAL_CONFLICT", "ERROR", "REVIEW_REQUIRED", "TEXT_ALIGNED"]
    inputs = [InputCase(id=str(i), claim_id=str(i), doc_id="1", claim="C", sentences=["E"])
              for i in range(5)]
    gold = [GoldCase(id=str(i), label=label, rationales=[[0]] if label != "NEI" else [])
            for i, label in enumerate(labels)]
    predictions = [Prediction(id=str(i), state=state, sentence_ids=[0] if i in {0, 4} else [],
                              evidence_text="E" if i in {0, 4} else "",
                              error="test failure" if state == "ERROR" else None)
                   for i, state in enumerate(states)]
    return inputs, gold, predictions


def test_scifact_counts_include_errors_and_abstentions():
    inputs, gold, predictions = sample_data()
    result = score_predictions("scifact_cited_abstract_v1", inputs, gold, predictions)
    assert result["total"] == 5 and result["errors"] == 1
    assert result["contradiction_alert_precision"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert result["contradiction_alert_recall"]["value"] == 0.5
    assert result["support_alert_rate"]["value"] == 0.5
    assert result["aligned_support_fraction"]["value"] == 1.0
    assert result["rationale_any_hit"]["value"] == 0.5
    assert result["state_by_gold"]["CONTRADICT"]["ERROR"] == 1
    assert "accuracy" not in result  # Review states are not three-way truth labels.


def test_unresolved_metric_counts_review_insufficient_and_errors_together():
    inputs, gold, predictions = sample_data()
    predictions[4] = Prediction(id="4", state="INSUFFICIENT_EVIDENCE")
    result = score_predictions("scifact_cited_abstract_v1", inputs, gold, predictions)
    assert result["rule_unresolved_rate"] == {"numerator": 3, "denominator": 5, "value": 0.6}
    assert result["concrete_rule_result_rate"] == {"numerator": 2, "denominator": 5, "value": 0.4}


def test_no_alerts_does_not_manufacture_perfect_precision():
    inputs, gold, _ = sample_data()
    predictions = [Prediction(id=item.id, state="REVIEW_REQUIRED") for item in inputs]
    result = score_predictions("scifact_cited_abstract_v1", inputs, gold, predictions)
    assert result["contradiction_alert_precision"]["value"] is None
    assert result["contradiction_alert_recall"]["value"] == 0.0
    assert result["review_required_rate"]["value"] == 1.0


@pytest.mark.parametrize("change", ["missing", "duplicate", "extra"])
def test_predictions_must_cover_exactly_the_input_ids(change):
    inputs, gold, predictions = sample_data()
    if change == "missing":
        predictions.pop()
    elif change == "duplicate":
        predictions.append(predictions[0])
    else:
        predictions.append(Prediction(id="unexpected", state="REVIEW_REQUIRED"))
    with pytest.raises(ValueError):
        score_predictions("scifact_cited_abstract_v1", inputs, gold, predictions)


def test_regression_requires_state_and_finding_codes():
    inputs = [InputCase(id="x", claim_id="x", doc_id="x", claim="C", sentences=["E"], category="numbers")]
    gold = [GoldCase(id="x", expected_state="POTENTIAL_CONFLICT", required_codes=["NUMBER_MISMATCH"])]
    predictions = [Prediction(id="x", state="POTENTIAL_CONFLICT")]
    result = score_predictions("semantic_regression_v1", inputs, gold, predictions)
    assert result["state_match"]["value"] == 1.0
    assert result["case_pass"]["value"] == 0.0


def test_unknown_protocol_cannot_receive_default_metrics():
    with pytest.raises(ValueError):
        score_predictions("unknown", *sample_data())


def test_partial_quote_does_not_count_as_complete_rationale():
    inputs = [InputCase(id="x", claim_id="1", doc_id="1", claim="C", sentences=["The treatment improves survival."])]
    gold = [GoldCase(id="x", label="SUPPORT", rationales=[[0]])]
    predictions = [Prediction(id="x", state="REVIEW_REQUIRED", evidence_text="improves survival", sentence_ids=[0])]
    result = score_predictions("scifact_cited_abstract_v1", inputs, gold, predictions)
    assert result["rationale_any_hit"]["value"] == 1.0
    assert result["rationale_complete_hit"]["value"] == 0.0


def test_scoring_rejects_invented_selected_sentence_ids():
    inputs, gold, predictions = sample_data()
    predictions[0].evidence_text = ""
    with pytest.raises(ValueError, match="excerpt"):
        score_predictions("scifact_cited_abstract_v1", inputs, gold, predictions)
