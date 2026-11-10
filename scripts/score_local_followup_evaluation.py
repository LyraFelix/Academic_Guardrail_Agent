"""Open selected-partition gold only after verifying a complete immutable run."""

import argparse
from collections import Counter
import json
from pathlib import Path

from academic_guardrail.core.review_store import ReviewStore
from benchmarks.client_comparison import MAPPING, arm_metrics, paired_metrics
from benchmarks.datasets import sha256
from benchmarks.local_followup_evaluation import (
    ARMS, bytes_digest, check_files, cost_summary, first_prompt, inspect_receipt,
    load_packet_view, load_plan, relative_file, second_prompt,
)
from benchmarks.metrics import rate
from scripts.run_paired_review import load_frozen_packet


def load_completed_run(run):
    manifest = json.loads((run / "manifest.json").read_bytes())
    if manifest.get("status") != "completed":
        raise ValueError("Incomplete run is not eligible for full paired scoring")
    check_files(run, manifest["files"])
    plan, _, _ = load_plan(run / "frozen" / "plan.json")
    if any(manifest[key] != plan[key] for key in ("protocol", "model", "reasoning")):
        raise ValueError("Run configuration differs from its frozen plan")
    if sha256(run / "plan.json") != manifest["plan_sha256"] or (run / "plan.json").read_bytes() != (
            run / "frozen" / "plan.json").read_bytes():
        raise ValueError("Run plan checksum differs from the frozen protocol")
    rows = json.loads((run / "rows.json").read_bytes())
    cases = json.loads((run / "cases.json").read_bytes())
    identifiers = [case["id"] for case in plan["cases"]]
    expected = {(identifier, arm) for identifier in identifiers for arm in ARMS}
    if len(rows) != len(expected) or {(row["id"], row["arm"]) for row in rows} != expected:
        raise ValueError("Results must cover exactly one row per frozen case and arm")
    if len(cases) != len(identifiers) or {row["id"] for row in cases} != set(identifiers):
        raise ValueError("Case outcomes must cover exactly the frozen cases, without duplicates")
    attempts = [json.loads(line) for line in (run / "attempts.jsonl").read_text(encoding="utf-8").splitlines()]
    indexed = {row["attempt"]: row for row in attempts}
    if len(indexed) != len(attempts) or len(attempts) != manifest["actual_cli_calls"]:
        raise ValueError("Actual invocation ledger contains missing or duplicate attempts")
    if manifest["completed_cases"] != len(identifiers) or len(attempts) > 3 * len(identifiers):
        raise ValueError("Completed run violates case count or actual call budget")
    requests = [json.loads(line) for line in (run / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
    if len(requests) != len(attempts) or {row["attempt"] for row in requests} != set(indexed):
        raise ValueError("Requests do not exactly match completed invocation receipts")
    requests_by_attempt = {row["attempt"]: row for row in requests}
    cases_by_id = {row["id"]: row for row in cases}
    plan_by_id = {row["id"]: row for row in plan["cases"]}
    receipts = {name: json.loads((relative_file(run, name) / "observed_receipt.json").read_bytes())
                for name in indexed}
    seen_threads = set()
    for attempt in attempts:
        directory = relative_file(run, attempt["attempt"])
        request = requests_by_attempt[attempt["attempt"]]
        if any(attempt.get(key) != value for key, value in request.items()):
            raise ValueError("Request fields differ from their corresponding invocation receipt")
        if attempt["id"] not in cases_by_id or attempt["stage"] not in {"initial", "fulltext_direct", "local_followup"}:
            raise ValueError("Request references an unknown case or decision stage")
        receipt = receipts[attempt["attempt"]]
        if receipt.get("tool_items") or receipt.get("event_stream_valid") is not True:
            raise ValueError("Completed run contains an unverifiable model isolation boundary")
        threads = receipt.get("thread_ids", [])
        if len(threads) != len(set(threads)) or seen_threads.intersection(threads):
            raise ValueError("Completed run contains reused model thread IDs")
        seen_threads.update(threads)
        if receipt.get("error") is None and len(threads) != 1:
            raise ValueError("Successful attempt lacks its unique model thread ID")
        packet = load_frozen_packet(run / "runtime", attempt)
        case, frozen_case = cases_by_id[attempt["id"]], plan_by_id[attempt["id"]]
        if attempt["stage"] in {"initial", "fulltext_direct"}:
            key = "abstract_packet" if attempt["stage"] == "initial" else "full_text_packet"
            frozen_view = load_packet_view(run / "frozen", frozen_case[key])
            if any(attempt[key] != frozen_view[key] for key in ("packet_id", "packet_sha256")):
                raise ValueError("Request used a different initial or full-text packet")
        else:
            context = ReviewStore(run / "runtime" / "stored").load_context(packet.packet_id)
            initial_record = case["initial_record"]
            if context is None or initial_record is None or context.parent_review_id != initial_record["review_id"] or (
                    context.parent_review_sha256 != initial_record["review_sha256"]):
                raise ValueError("Follow-up request does not link to its actual shared initial record")
        replay = inspect_receipt(packet, receipt)
        if any(attempt[key] != value for key, value in replay.items()):
            raise ValueError("Saved raw prediction or validation differs from its model receipt")
        prompt_bytes = relative_file(run, attempt["prompt_file"]).read_bytes()
        if bytes_digest(prompt_bytes) != attempt["prompt_sha256"]:
            raise ValueError("Dynamic prompt checksum changed")
        view = packet.model_dump(mode="json")
        expected_prompt = first_prompt(view) if attempt["stage"] == "initial" else second_prompt(
            view, receipts[case["initial_attempt"]].get("response"))
        if prompt_bytes != expected_prompt.encode("utf-8") or (directory / "prompt.txt").read_bytes() != prompt_bytes:
            raise ValueError("Prompt differs from its frozen renderer, actual packet or raw shared judgment")
    for case in cases:
        initial = indexed[case["initial_attempt"]]
        direct = indexed[case["direct_final_attempt"]]
        local = indexed[case["local_final_attempt"]]
        if initial["stage"] != "initial" or direct["stage"] != "fulltext_direct" or local["stage"] not in {
                "initial", "local_followup"} or any(row["id"] != case["id"] for row in (initial, direct, local)):
            raise ValueError("Case outcomes reference the wrong decision stage or case")
        if sum(row["id"] == case["id"] for row in attempts) != (2 + (local["stage"] == "local_followup")):
            raise ValueError("Case invocation count violates the two-call effective budget")
    for row in rows:
        final = indexed.get(row["attempt"])
        cost_ids = row["cost_attempts"]
        if final is None or final["id"] != row["id"] or len(cost_ids) != len(set(cost_ids)) or not 1 <= len(cost_ids) <= 2:
            raise ValueError("Arm references a missing attempt or violates its effective budget")
        if any(name not in indexed or indexed[name]["id"] != row["id"] for name in cost_ids):
            raise ValueError("Arm costs reference another case or a missing attempt")
        if any(row[key] != final[key] for key in (
                "prediction", "validation_error", "quote_count", "exact_quote_count", "usage", "elapsed_seconds")):
            raise ValueError("Arm result differs from its immutable raw final judgment")
        case = next(item for item in cases if item["id"] == row["id"])
        expected_final = case["initial_attempt"] if row["arm"] == "abstract_only" else case[
            "direct_final_attempt" if row["arm"] == "fulltext_direct" else "local_final_attempt"]
        expected_cost = [case["initial_attempt"]]
        if expected_final != case["initial_attempt"]:
            expected_cost.append(expected_final)
        if row["attempt"] != expected_final or cost_ids != expected_cost:
            raise ValueError("Arm omits or double counts the shared initial invocation")
    return manifest, plan, rows, cases, attempts


def read_gold(path, expected_hash, identifiers):
    raw = path.read_bytes()
    if bytes_digest(raw) != expected_hash:
        raise ValueError("Gold checksum differs from the selected partition frozen before judgments")
    records = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if len(records) != len(identifiers) or {row["id"] for row in records} != set(identifiers):
        raise ValueError("Gold must contain exactly the selected frozen partition without duplicate cases")
    allowed = {"SUPPORTED", "CONTRADICTED", "NOT_ENOUGH_EVIDENCE"}
    if any(row.get(key) not in allowed for row in records for key in ("fulltext_label", "abstract_only_label")):
        raise ValueError("Gold uses an unsupported reference label")
    return {scope: {row["id"]: MAPPING[row[key]] for row in records}
            for scope, key in (("full_text", "fulltext_label"), ("abstract", "abstract_only_label"))}


def count_rate(identifiers, total):
    return {"count": len(identifiers), "denominator": total, "rate": rate(len(identifiers), total),
            "case_ids": identifiers}


def summarize_arm(rows, gold, attempts):
    indexed = {row["attempt"]: row for row in attempts}
    charged = [indexed[name] for row in rows for name in row["cost_attempts"]]
    metric_rows = []
    for row in rows:
        cost = cost_summary([indexed[name] for name in row["cost_attempts"]])
        metric_rows.append({**row, "usage": cost["reported_tokens"] if cost["usage_recorded_calls"] else None,
                            "elapsed_seconds": cost["elapsed_seconds"]})
    concrete = [row for row in rows if row["prediction"] in {"SUPPORT", "CONTRADICT"}]
    correct = [row["id"] for row in concrete if row["prediction"] == gold[row["id"]]]
    false = [row["id"] for row in concrete if row["prediction"] != gold[row["id"]]]
    return {"metrics": arm_metrics(metric_rows, gold), "cost": cost_summary(charged),
            "correct_concrete": count_rate(correct, len(rows)),
            "false_concrete": count_rate(false, len(rows)),
            "false_concrete_among_concrete": count_rate(false, len(concrete)),
            "remaining_nei": sum(row["prediction"] == "NEI" for row in rows),
            "remaining_uncertain": sum(row["prediction"] == "ABSTAIN" for row in rows),
            "workflow_error_cases": sum(bool(row["workflow_errors"]) for row in rows),
            "record_accepted_cases": sum(row["record_accepted"] for row in rows),
            "final_attempts": {row["id"]: row["attempt"] for row in rows}}


def score(run, gold_path, destination):
    run, gold_path, destination = (Path(value).resolve() for value in (run, gold_path, destination))
    if destination.is_relative_to(run):
        raise ValueError("Save score outside the immutable run directory")
    manifest, plan, rows, cases, attempts = load_completed_run(run)
    # This is deliberately after every completeness/integrity/budget check above.
    gold = read_gold(gold_path, plan["expected_gold_sha256"], [case["id"] for case in plan["cases"]])
    grouped = {arm: [row for row in rows if row["arm"] == arm] for arm in ARMS}
    direct, local = grouped["fulltext_direct"], grouped["local_followup"]
    direct_by_id = {row["id"]: row for row in direct}
    concrete_wins, concrete_losses = [], []
    for row in local:
        label = gold["full_text"][row["id"]]
        left = direct_by_id[row["id"]]["prediction"] == label and label != "NEI"
        right = row["prediction"] == label and label != "NEI"
        if right and not left:
            concrete_wins.append(row["id"])
        if left and not right:
            concrete_losses.append(row["id"])
    unresolved = [case for case in cases if case["unresolved_initial"]]
    requested = [case for case in cases if case["lookup_requested"]]
    retrieval = {"total_cases": len(cases), "unresolved_initial": len(unresolved),
                 "unresolved_with_declared_gap": sum(case["declared_gap_count"] > 0 for case in unresolved),
                 "requested": len(requested),
                 "query_coverage_of_unresolved": rate(len(requested), len(unresolved)),
                 "status_counts": dict(Counter(case["retrieval_status"] for case in cases)),
                 "cases_with_added_evidence": sum(bool(case["added_evidence_ids"]) for case in cases),
                 "queries": [{"id": case["id"], "terms": case["query_terms"],
                              "status": case["retrieval_status"], "added_units": len(case["added_evidence_ids"])}
                             for case in requested],
                 "boundary": "Query coverage is attempted lookup / unresolved initial cases; lexical retrieval is not gold-rationale recall or semantic resolution."}
    result = {"protocol": plan["protocol"], "partition": plan["partition"],
              "requested_model": manifest["model"], "reasoning": manifest["reasoning"],
              "cli_version": manifest["cli_version"], "run_manifest_sha256": sha256(run / "manifest.json"),
              "gold_sha256": plan["expected_gold_sha256"],
              "arms": {arm: summarize_arm(grouped[arm], gold["abstract" if arm == "abstract_only" else "full_text"], attempts)
                       for arm in ARMS},
              "paired_full_text": {"left": "fulltext_direct", "right": "local_followup",
                                   **paired_metrics(direct, local, gold["full_text"])},
              "paired_correct_concrete": {"right_wins": concrete_wins, "right_losses": concrete_losses,
                                          "ties": len(cases) - len(concrete_wins) - len(concrete_losses)},
              "retrieval": retrieval, "actual_cost": cost_summary(attempts),
              "shared_initial_cost": cost_summary([row for row in attempts if row["stage"] == "initial"]),
              "raw_attempt_errors": [{"id": row["id"], "stage": row["stage"], "error": row["error"]}
                                     for row in attempts if row["error"] is not None],
              "raw_validation_rejections": [{"id": row["id"], "stage": row["stage"],
                                             "error": row["validation_error"]} for row in attempts
                                            if row["validation_error"] is not None],
              "workflow_errors": [{"id": case["id"], "errors": case["workflow_errors"]} for case in cases
                                  if case["workflow_errors"]],
              "elapsed_wall_seconds": manifest["elapsed_seconds"],
              "boundary": plan["rules"]["boundary"],
              "interpretation": "Abstract-only agreement uses abstract gold; both workflow finals use full-text gold. NEI is not a solved concrete judgment. Raw label changes alone are not improvements. Quote/record acceptance checks provenance, not semantics. Each arm cost includes the shared first call; actual_cost counts it once. No currency-cost or human-gold claim; paired p-values are descriptive/exploratory."}
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = score(args.run, args.gold, args.output)
    print(json.dumps({"partition": result["partition"], "actual_calls": result["actual_cost"]["model_calls"],
                      "arms": {name: value["correct_concrete"] for name, value in result["arms"].items()}}))


if __name__ == "__main__":
    main()
