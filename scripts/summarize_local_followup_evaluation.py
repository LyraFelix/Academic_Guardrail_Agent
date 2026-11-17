"""Revalidate and pool disjoint frozen runs; write descriptive JSON and a case CSV."""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path

from benchmarks.datasets import sha256
from benchmarks.local_followup_evaluation import ARMS, cost_summary
from scripts.score_local_followup_evaluation import (
    load_completed_run, read_gold, summarize_arm, summarize_pair,
)


def validate_batch_selection(plans):
    """Prevent changed configurations, duplicate cases and papers crossing partitions."""
    if not plans:
        raise ValueError("Provide at least one completed batch")
    configuration = tuple(plans[0][key] for key in ("protocol", "model", "reasoning"))
    seen_cases, paper_partitions, source_partitions = set(), {}, {}
    for plan in plans:
        if tuple(plan[key] for key in ("protocol", "model", "reasoning")) != configuration:
            raise ValueError("Cannot combine mixed protocol, model or reasoning configurations")
        identifiers = [case["id"] for case in plan["cases"]]
        if len(identifiers) != len(set(identifiers)) or seen_cases.intersection(identifiers):
            raise ValueError("Batch case IDs overlap or contain duplicates")
        seen_cases.update(identifiers)
        partition = plan["partition"]
        for case in plan["cases"]:
            paper = case["input"]["paper_id"]
            if paper in paper_partitions and paper_partitions[paper] != partition:
                raise ValueError("Paper partition leakage: a paper occurs in multiple partitions")
            paper_partitions[paper] = partition
        # Detect a copied source under another paper ID as well.
        for digest in plan["source_sha256"].values():
            if digest in source_partitions and source_partitions[digest] != partition:
                raise ValueError("Source partition leakage: identical bytes occur in multiple partitions")
            source_partitions[digest] = partition


def comparison_summary(rows, gold, attempts):
    grouped = {arm: [row for row in rows if row["arm"] == arm] for arm in ARMS}
    return {"arms": {arm: summarize_arm(grouped[arm], gold["abstract" if arm == "abstract_only" else "full_text"], attempts)
                     for arm in ARMS},
            "paired_primary": summarize_pair(grouped["fulltext_single"], grouped["local_followup"], gold["full_text"]),
            "paired_secondary": summarize_pair(grouped["fulltext_direct"], grouped["local_followup"], gold["full_text"])}


def summarize(batches, destination, case_csv):
    batches = [(Path(run).resolve(), Path(gold).resolve()) for run, gold in batches]
    destination, case_csv = Path(destination).resolve(), Path(case_csv).resolve()
    if destination == case_csv or destination.exists() or case_csv.exists():
        raise ValueError("Use two distinct new summary output paths")
    if any(path.is_relative_to(run) for run, _ in batches for path in (destination, case_csv)):
        raise ValueError("Save summaries outside every immutable run directory")
    # Verify ALL runs and their relationships before opening ANY reference labels.
    seen_threads = set()
    loaded = [load_completed_run(run, seen_threads=seen_threads) for run, _ in batches]
    validate_batch_selection([plan for _, plan, _, _, _ in loaded])
    gold, rows, attempts, outcomes, inputs, batch_records = {"abstract": {}, "full_text": {}}, [], [], {}, {}, []
    for index, ((run, gold_path), (manifest, plan, batch_rows, cases, batch_attempts)) in enumerate(zip(batches, loaded)):
        labels = read_gold(gold_path, plan["expected_gold_sha256"], [case["id"] for case in plan["cases"]])
        for scope in gold:
            gold[scope].update(labels[scope])
        inputs.update({case["id"]: case["input"] for case in plan["cases"]})
        outcomes.update({case["id"]: case for case in cases})
        # Every run starts attempt_000; namespace identifiers before adding costs.
        names = {attempt["attempt"]: f"batch_{index:03d}/{attempt['attempt']}" for attempt in batch_attempts}
        attempts.extend({**attempt, "attempt": names[attempt["attempt"]]} for attempt in batch_attempts)
        rows.extend({**row, "attempt": names[row["attempt"]],
                     "cost_attempts": [names[name] for name in row["cost_attempts"]]} for row in batch_rows)
        batch_records.append({"run": str(run), "partition": plan["partition"], "cases": len(cases),
                              "papers": sorted({case["input"]["paper_id"] for case in plan["cases"]}),
                              "run_manifest_sha256": sha256(run / "manifest.json"),
                              "plan_sha256": manifest["plan_sha256"], "gold_sha256": plan["expected_gold_sha256"],
                              "cli_version": manifest["cli_version"], "actual_cli_calls": len(batch_attempts),
                              "max_actual_cli_calls": plan["max_actual_cli_calls"],
                              "elapsed_wall_seconds": manifest["elapsed_seconds"]})
    per_paper = []
    for partition, paper in sorted({(item["partition"], item["paper_id"]) for item in inputs.values()}):
        identifiers = {identifier for identifier, item in inputs.items()
                       if (item["partition"], item["paper_id"]) == (partition, paper)}
        paper_rows = [row for row in rows if row["id"] in identifiers]
        paper_gold = {scope: {key: value for key, value in labels.items() if key in identifiers}
                      for scope, labels in gold.items()}
        per_paper.append({"partition": partition, "paper_id": paper, "cases": len(identifiers),
                          "fulltext_gold_counts": dict(Counter(paper_gold["full_text"].values())),
                          **comparison_summary(paper_rows, paper_gold, attempts)})
    first_plan = loaded[0][1]
    stage_costs = {stage: cost_summary([attempt for attempt in attempts if attempt["stage"] == stage])
                   for stage in ("initial", "fulltext_single", "fulltext_direct", "local_followup")}
    result = {"protocol": first_plan["protocol"], "requested_model": first_plan["model"],
              "reasoning": first_plan["reasoning"], "cases": len(inputs), "papers": len(per_paper),
              "batches": batch_records, "max_actual_cli_calls": sum(item["max_actual_cli_calls"] for item in batch_records),
              **comparison_summary(rows, gold, attempts), "per_paper": per_paper,
              "actual_cost": cost_summary(attempts), "stage_costs": stage_costs,
              "shared_initial_cost": stage_costs["initial"],
              "retrieval_status_counts": dict(Counter(case["retrieval_status"] for case in outcomes.values())),
              "boundary": first_plan["rules"]["boundary"],
              "interpretation": "Source-based authored cases and reference labels, not human-expert gold or general accuracy. "
                                "All cases, errors and rejected records remain in denominators. Refutation recall uses all gold "
                                "CONTRADICTED cases; precision uses all predicted refutations. Avoidable NEI uses gold SUPPORTED/CONTRADICTED. "
                                "Wilson intervals and paired p-values are descriptive; cases within papers are not independent samples. "
                                "Single-call full text pays only its one call; both two-stage arms include the shared initial; actual cost "
                                "counts each invocation once. Reasoning tokens are part of output and never added again. Unknown usage is null."}
    if result["actual_cost"]["model_calls"] > result["max_actual_cli_calls"]:
        raise ValueError("Combined actual calls exceed the sum of frozen budgets")
    compact = []
    for identifier, item in inputs.items():
        predictions = {row["arm"]: row for row in rows if row["id"] == identifier}
        label = gold["full_text"][identifier]
        local_correct = predictions["local_followup"]["prediction"] == label
        compact.append({"id": identifier, "partition": item["partition"], "paper_id": item["paper_id"],
                        "abstract_gold": gold["abstract"][identifier], "fulltext_gold": label,
                        **{arm: predictions[arm]["prediction"] for arm in ARMS},
                        "primary_correctness_delta": int(local_correct) - int(predictions["fulltext_single"]["prediction"] == label),
                        "secondary_correctness_delta": int(local_correct) - int(predictions["fulltext_direct"]["prediction"] == label),
                        "retrieval_status": outcomes[identifier]["retrieval_status"],
                        "local_record_accepted": predictions["local_followup"]["record_accepted"],
                        "local_workflow_errors": " | ".join(outcomes[identifier]["workflow_errors"]),
                        **{f"{arm}_calls": len(predictions[arm]["cost_attempts"]) for arm in ARMS}})
    with case_csv.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(compact[0]))
        writer.writeheader()
        writer.writerows(compact)
    result["case_csv"] = {"path": str(case_csv), "sha256": sha256(case_csv)}
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", nargs=2, action="append", metavar=("RUN", "GOLD"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases-csv", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.batch, args.output, args.cases_csv)
    print(json.dumps({"cases": result["cases"], "actual_calls": result["actual_cost"]["model_calls"],
                      "max_calls": result["max_actual_cli_calls"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
