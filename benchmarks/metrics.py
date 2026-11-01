"""Native-state diagnostics, with explicit denominators and no invented labels."""

from benchmarks.datasets import unique_by_id
from benchmarks.schema import LABELS, STATES
from benchmarks.predictors import sentence_ids_for_excerpt


def rate(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def score_predictions(protocol, inputs, gold, predictions):
    indexed_inputs, indexed_gold, indexed_predictions = map(unique_by_id, (inputs, gold, predictions))
    if not inputs or set(indexed_inputs) != set(indexed_gold) or set(indexed_inputs) != set(indexed_predictions):
        raise ValueError("Scoring requires exactly one gold and prediction row per input")
    rows = [(item, indexed_gold[item.id], indexed_predictions[item.id]) for item in inputs]
    for item, label, prediction in rows:
        if any(i < 0 or i >= len(item.sentences) for i in prediction.sentence_ids):
            raise ValueError(f"Invalid predicted sentence index: {item.id}")
        if prediction.sentence_ids != sentence_ids_for_excerpt(item.sentences, prediction.evidence_text):
            raise ValueError(f"Predicted IDs do not match the returned excerpt: {item.id}")
        if (prediction.state == "ERROR") != bool(prediction.error):
            raise ValueError(f"Inconsistent error record: {item.id}")
    common = {"protocol": protocol, "total": len(rows), "claims": len({item.claim_id for item in inputs}),
              "errors": sum(p.state == "ERROR" for _, _, p in rows),
              "state_counts": {state: sum(p.state == state for _, _, p in rows) for state in STATES}}
    unresolved = sum(common["state_counts"][state] for state in ("REVIEW_REQUIRED", "INSUFFICIENT_EVIDENCE", "ERROR"))
    common["rule_unresolved_rate"] = rate(unresolved, len(rows))
    common["concrete_rule_result_rate"] = rate(len(rows) - unresolved, len(rows))
    if protocol == "semantic_regression_v1":
        if any(g.expected_state is None or g.label is not None for _, g, _ in rows):
            raise ValueError("Regression labels require expected_state only")
        passed = lambda g, p: p.state == g.expected_state and set(g.required_codes) <= {f.get("code") for f in p.findings}
        common.update({"evidence_boundary": "development_regression_not_held_out_accuracy",
                       "state_match": rate(sum(g.expected_state == p.state for _, g, p in rows), len(rows)),
                       "case_pass": rate(sum(passed(g, p) for _, g, p in rows), len(rows)),
                       "categories": {category: rate(sum(passed(g, p) for i, g, p in rows if i.category == category),
                                                     sum(i.category == category for i, _, _ in rows))
                                      for category in sorted({i.category or "unspecified" for i in inputs})}})
        return common
    if protocol != "scifact_cited_abstract_v1":
        raise ValueError(f"Unknown scoring protocol: {protocol}")
    if any(g.label is None or g.expected_state is not None for _, g, _ in rows):
        raise ValueError("SciFact labels require label only")
    table = {label: {state: sum(g.label == label and p.state == state for _, g, p in rows)
                     for state in STATES} for label in LABELS}
    totals = {label: sum(table[label].values()) for label in LABELS}
    alerts = sum(table[label]["POTENTIAL_CONFLICT"] for label in LABELS)
    aligned = sum(table[label]["TEXT_ALIGNED"] for label in LABELS)
    evidence_rows = [(i, g, p) for i, g, p in rows if g.label != "NEI"]
    common.update({
        "evidence_boundary": "given_cited_abstract_diagnostic_not_official_scifact_score",
        "state_by_gold": table, "gold_counts": totals,
        "contradiction_alert_precision": rate(table["CONTRADICT"]["POTENTIAL_CONFLICT"], alerts),
        "contradiction_alert_recall": rate(table["CONTRADICT"]["POTENTIAL_CONFLICT"], totals["CONTRADICT"]),
        "support_alert_rate": rate(table["SUPPORT"]["POTENTIAL_CONFLICT"], totals["SUPPORT"]),
        "nei_alert_rate": rate(table["NEI"]["POTENTIAL_CONFLICT"], totals["NEI"]),
        "aligned_support_fraction": rate(table["SUPPORT"]["TEXT_ALIGNED"], aligned),
        "contradiction_aligned_rate": rate(table["CONTRADICT"]["TEXT_ALIGNED"], totals["CONTRADICT"]),
        "review_required_rate": rate(common["state_counts"]["REVIEW_REQUIRED"], len(rows)),
        "rationale_any_hit": rate(sum(any(set(r) & set(p.sentence_ids) for r in g.rationales) for _, g, p in evidence_rows), len(evidence_rows)),
        "rationale_complete_hit": rate(sum(any(set(r) <= set(sentence_ids_for_excerpt(i.sentences, p.evidence_text, full_sentences=True))
                                                    for r in g.rationales) for i, g, p in evidence_rows), len(evidence_rows)),
    })
    return common
