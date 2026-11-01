"""Score frozen attempts against pinned gold; include every planned case per arm."""

import argparse
import hashlib
import itertools
import json
from pathlib import Path

from benchmarks.client_comparison import ARMS, arm_metrics, paired_metrics
from benchmarks.datasets import sha256, unique_by_id
from benchmarks.schema import GoldCase


def score(run, gold_path, destination):
    manifest = json.loads((run / "manifest.json").read_bytes())
    if manifest["status"] != "completed":
        raise ValueError("Incomplete comparison; report attempted/remaining work, not a full paired score")
    for filename, digest in manifest["files"].items():
        path = (run / filename).resolve()
        if not path.is_relative_to(run.resolve()) or sha256(path) != digest:
            raise ValueError(f"Run artifact changed: {filename}")
    plan = json.loads((run / "plan.json").read_bytes())
    if sha256(run / "plan.json") != manifest["plan_sha256"]:
        raise ValueError("Run plan checksum mismatch")
    raw_gold = gold_path.read_bytes()
    if hashlib.sha256(raw_gold).hexdigest() != plan["expected_gold_sha256"]:
        raise ValueError("Gold differs from snapshot frozen before judging")
    gold = {key: item.label for key, item in unique_by_id([
        GoldCase.model_validate_json(line) for line in raw_gold.decode("utf-8").splitlines() if line.strip()]).items()}
    rows = json.loads((run / "rows.json").read_bytes())
    expected = {(item["id"], item["arm"]) for item in plan["schedule"]}
    if len(rows) != len(expected) or {(row["id"], row["arm"]) for row in rows} != expected:
        raise ValueError("Rows do not cover the full frozen schedule")
    grouped = {arm: [row for row in rows if row["arm"] == arm] for arm in ARMS}
    for group in grouped.values():
        if {row["id"] for row in group} != set(gold):
            raise ValueError("Gold and every arm must cover identical cases")
    result = {"protocol": plan["protocol"], "requested_model": manifest["model"],
              "reasoning": manifest["reasoning"], "cli_version": manifest["cli_version"],
              "run_manifest_sha256": sha256(run / "manifest.json"),
              "gold_sha256": plan["expected_gold_sha256"],
              "arms": {arm: arm_metrics(group, gold) for arm, group in grouped.items()},
              "pairs": {f"{left}_to_{right}": paired_metrics(grouped[left], grouped[right], gold)
                        for left, right in itertools.combinations(ARMS, 2)},
              "cases": [{**row, "gold": gold[row["id"]], "correct": row["prediction"] == gold[row["id"]]} for row in rows],
              "mcp_record_seconds": manifest["mcp_record_seconds"],
              "boundary": "Raw model labels are primary; all arms use the same offline acceptance check; MCP also records over transport. Small public-train exploratory sample, no confirmed generalization or human-time/currency savings."}
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = score(args.run, args.gold, args.output)
    print(json.dumps({arm: values["raw_accuracy"] for arm, values in result["arms"].items()}))
