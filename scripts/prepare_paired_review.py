"""Freeze a new balanced dataset, actual MCP packets and all three-arm prompts.

Only this preparation step uses labels for sampling. The model runner reads the
plan and prompt files, never gold. Run as python -m scripts.prepare_paired_review.
"""

import argparse
import asyncio
import hashlib
import io
import json
from pathlib import Path
import tarfile

from academic_guardrail.core.review_models import ClientJudgment
from benchmarks.client_comparison import ARMS, COMPARISON_PROTOCOL, make_prompt, shared_evidence
from benchmarks.datasets import SCIFACT_SOURCE, _archive_records, _raw_index, _write_dataset, sha256, unique_by_id, write_json
from benchmarks.runner import _code_record
from benchmarks.schema import GoldCase, InputCase
from scripts.client_review_batch import load_batch, prepare as prepare_batch
from scripts.codex_review_client import MODEL, REASONING, strict_schema
from scripts.prepare_client_evaluation import select_partition


def prepare_dataset(archive_path, exclusion_paths, destination, per_class):
    raw = archive_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SCIFACT_SOURCE["sha256"]:
        raise ValueError("Official archive checksum mismatch")
    snapshots = [path.read_bytes() for path in exclusion_paths]
    previous = unique_by_id([InputCase.model_validate_json(line) for data in snapshots
                             for line in data.decode("utf-8").splitlines() if line.strip()])
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        corpus = _raw_index(_archive_records(archive, "data/corpus.jsonl"), "doc_id")
        claims = _raw_index(_archive_records(archive, "data/claims_train.jsonl"), "id")
    candidates, gold = [], {}
    for cid, claim in claims.items():
        for did in set(claim["cited_doc_ids"]):
            annotations = claim["evidence"].get(str(did), [])
            labels = {item["label"] for item in annotations}
            if len(labels) > 1 or labels - {"SUPPORT", "CONTRADICT"}:
                raise ValueError("Invalid source labels")
            label = next(iter(labels)) if labels else "NEI"
            candidates.append((str(cid), str(did), label))
            gold[f"{cid}:{did}"] = GoldCase(id=f"{cid}:{did}", label=label,
                                          rationales=[item["sentences"] for item in annotations])
    selected = select_partition(candidates, per_class, "contradiction_comparison_v1",
                                {row.claim_id for row in previous.values()},
                                {row.doc_id for row in previous.values()})
    inputs = [InputCase(id=f"{cid}:{did}", claim_id=cid, doc_id=did,
                        claim=claims[int(cid)]["claim"], sentences=corpus[int(did)]["abstract"])
              for cid, did, _ in selected]
    destination.mkdir(parents=True, exist_ok=False)
    for index, data in enumerate(snapshots):
        (destination / f"exclusions_{index + 1}.jsonl").write_bytes(data)
    source = {**SCIFACT_SOURCE, "name": "SciFact public train paired client comparison",
              "split": "train", "selection_uses_gold_labels": True,
              "partition": "contradiction_comparison_v1", "seed": "client-evaluation-v1",
              "per_class": per_class, "excluded_pairs": len(previous),
              "exclusion_hashes": [hashlib.sha256(data).hexdigest() for data in snapshots]}
    _write_dataset(destination / "dataset", inputs, [gold[row.id] for row in inputs],
                   "scifact_cited_abstract_v1", source)


def freeze_plan(batch, destination):
    """A plan contains all expected decisions and prompt bytes before any model call."""
    manifest, packets = load_batch(batch)
    destination.mkdir(parents=True, exist_ok=False)
    schema = strict_schema(ClientJudgment.model_json_schema())
    write_json(destination / "schema.json", schema)
    schedule = []
    for index, packet in enumerate(packets):
        order = ARMS[index % len(ARMS):] + ARMS[:index % len(ARMS)]
        for arm in order:
            filename = f"{index:03d}_{arm}.txt"
            (destination / filename).write_bytes(make_prompt(packet, arm).encode("utf-8"))
            schedule.append({"id": packet["id"], "arm": arm, "prompt_file": filename,
                             "prompt_sha256": sha256(destination / filename),
                             "evidence_sha256": hashlib.sha256(json.dumps(shared_evidence(packet), ensure_ascii=False,
                                                                         sort_keys=True).encode()).hexdigest()})
    plan = {"protocol": COMPARISON_PROTOCOL, "code": _code_record(), "arms": ARMS,
            "cases": len(packets), "decisions": len(schedule), "schedule": schedule,
            "model": MODEL, "reasoning": REASONING, "batch_manifest_sha256": sha256(batch / "manifest.json"),
            "schema_sha256": sha256(destination / "schema.json"),
            "expected_gold_sha256": manifest["expected_gold_sha256"],
            "primary_comparison": "mcp versus direct; raw CONTRADICT recall/precision",
            "secondary_comparisons": "guided_direct isolates prompting; all p-values exploratory",
            "budget": "one CLI invocation per arm/case, no harness retries or repair; CLI transport retries may be internal",
            "boundary": "structured-output direct control; no independent bare Responses API or dollar-cost claim"}
    write_json(destination / "plan.json", plan)
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--exclude-inputs", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--per-class", type=int, default=10)
    args = parser.parse_args()
    prepare_dataset(args.archive, args.exclude_inputs, args.output, args.per_class)
    dataset, batch = args.output / "dataset", args.output / "batch"
    asyncio.run(prepare_batch(dataset / "inputs.jsonl", batch, dataset / "manifest.json"))
    plan = freeze_plan(batch, args.output / "plan")
    print(json.dumps({"cases": plan["cases"], "decisions": plan["decisions"], "gold_not_printed": True}))


if __name__ == "__main__":
    main()
