"""Readable per-case exports; scoring decisions live in metrics.py."""

import csv
from collections import Counter

from benchmarks.datasets import unique_by_id, write_json


def _ratio(value):
    percentage = "undefined" if value["value"] is None else f'{100 * value["value"]:.2f}%'
    return f'{percentage} ({value["numerator"]}/{value["denominator"]})'


def write_reports(destination, metrics, inputs, gold, predictions):
    labels, outputs = unique_by_id(gold), unique_by_id(predictions)
    rows, failures = [], []
    for item in inputs:
        label, output = labels[item.id], outputs[item.id]
        codes = [finding.get("code", "") for finding in output.findings]
        issue = []
        if output.state == "ERROR":
            issue.append("execution_error")
        if label.label == "CONTRADICT" and output.state != "POTENTIAL_CONFLICT":
            issue.append("missed_contradiction_alert")
        if label.label in {"SUPPORT", "NEI"} and output.state == "POTENTIAL_CONFLICT":
            issue.append("alert_without_contradiction_label")
        if label.label in {"CONTRADICT", "NEI"} and output.state == "TEXT_ALIGNED":
            issue.append("alignment_without_support_label")
        if label.expected_state and (label.expected_state != output.state or not set(label.required_codes) <= set(codes)):
            issue.append("regression_failure")
        row = {"id": item.id, "claim_id": item.claim_id, "doc_id": item.doc_id,
               "gold": label.label or label.expected_state, "state": output.state,
               "score": output.score, "codes": ",".join(codes), "issue": ",".join(issue),
               "claim": item.claim, "excerpt": output.evidence_text, "error": output.error or ""}
        rows.append(row)
        if issue:
            failures.append({**row, "sentences": item.sentences, "rationales": label.rationales,
                             "selected_sentence_ids": output.sentence_ids, "findings": output.findings})
    with (destination / "cases.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    write_json(destination / "failures.json", failures)
    lines = ["# Evaluation summary", "", f'Protocol: `{metrics["protocol"]}`.',
             f'Claims: {metrics["claims"]}; pairs/cases: {metrics["total"]}; execution errors: {metrics["errors"]}.',
             "", "These are native-state diagnostics, not scientific truth accuracy or an official SciFact score.",
             "TEXT_ALIGNED still requires human review. REVIEW_REQUIRED is a state frequency, not measured human workload.",
             "rule_unresolved_rate includes REVIEW_REQUIRED, INSUFFICIENT_EVIDENCE and ERROR; concrete results are not scientific truth certification.",
             "", "| State | Count |", "| --- | --- |"]
    lines.extend(f"| {state} | {count} |" for state, count in metrics["state_counts"].items())
    lines.extend(["", "| Diagnostic | Value (numerator/denominator) |", "| --- | --- |"])
    for name, value in metrics.items():
        if isinstance(value, dict) and "numerator" in value:
            lines.append(f"| {name} | {_ratio(value)} |")
    if "state_by_gold" in metrics:
        states = list(metrics["state_counts"])
        lines.extend(["", "| Gold | " + " | ".join(states) + " |", "| --- | " + " | ".join("---" for _ in states) + " |"])
        lines.extend("| " + label + " | " + " | ".join(str(counts[s]) for s in states) + " |"
                     for label, counts in metrics["state_by_gold"].items())
    counts = Counter(code for prediction in predictions for code in {f.get("code", "") for f in prediction.findings})
    lines.extend(["", "Finding counts are cases containing a code (codes can overlap):", ""])
    lines.extend(f"- {code}: {count}" for code, count in counts.most_common())
    lines.extend(["", "`cases.tsv` contains every case; `failures.json` preserves every selected diagnostic failure, not a cherry-picked sample.",
                  "An unflagged contradiction may have been sent to review; a warning on SUPPORT can reflect a wording concern outside SciFact's task.",
                  "Rationale any-hit counts sentence overlap with the primary excerpt; complete-hit requires every sentence of one annotated rationale to be fully quoted.", ""])
    (destination / "summary.md").write_text("\n".join(lines), encoding="utf-8")
