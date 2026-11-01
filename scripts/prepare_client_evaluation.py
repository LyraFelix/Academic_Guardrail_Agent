"""Prepare balanced, claim/document-disjoint public-train diagnostic partitions.

Unlike the original natural sample, this selection uses labels for stratification.
Only input files are shown to the judging client; gold remains separate.
"""

import argparse
from collections import Counter
import hashlib
import io
from pathlib import Path
import tarfile

from benchmarks.datasets import SCIFACT_SOURCE, _archive_records, _raw_index, _write_dataset, sha256, unique_by_id, write_json
from benchmarks.schema import GoldCase, InputCase

LABELS = ("SUPPORT", "CONTRADICT", "NEI")
SEED = "client-evaluation-v1"


def rank(*parts):
    return hashlib.sha256(":".join((SEED, *parts)).encode()).hexdigest()


def select_partition(candidates, per_class, partition, used_claims, used_documents):
    """Select in seeded order, without allowing related pairs into another split."""
    if per_class < 1:
        raise ValueError("Class quota must be positive")
    selected, counts = [], Counter()
    ordered = sorted(candidates, key=lambda row: rank("selection", partition, row[0], row[1]))
    for claim_id, doc_id, label in ordered:
        if label not in LABELS:
            raise ValueError("Unknown fact label")
        if counts[label] == per_class or claim_id in used_claims or doc_id in used_documents:
            continue
        selected.append((claim_id, doc_id, label))
        counts[label] += 1
        used_claims.add(claim_id)
        used_documents.add(doc_id)
    if any(counts[label] != per_class for label in LABELS):
        raise ValueError(f"Cannot fill class quota without repeating claims/documents: {dict(counts)}")
    # Hide class grouping in the input order; label is never an ordering key.
    return sorted(selected, key=lambda row: rank("presentation", partition, row[0], row[1]))


def prepare(archive_path, prior_inputs, destination, discovery_per_class=12, validation_per_class=8):
    archive_bytes = archive_path.read_bytes()
    if hashlib.sha256(archive_bytes).hexdigest() != SCIFACT_SOURCE["sha256"]:
        raise ValueError("Official archive checksum mismatch")
    prior_bytes = prior_inputs.read_bytes()
    previous = [InputCase.model_validate_json(line) for line in prior_bytes.decode("utf-8").splitlines() if line.strip()]
    unique_by_id(previous)
    used_claims = {row.claim_id for row in previous}
    used_documents = {row.doc_id for row in previous}
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        corpus = _raw_index(_archive_records(archive, "data/corpus.jsonl"), "doc_id")
        claims = _raw_index(_archive_records(archive, "data/claims_train.jsonl"), "id")
    candidates, gold_by_pair = [], {}
    for claim_id, claim in claims.items():
        for doc_id in set(claim["cited_doc_ids"]):
            annotations = claim["evidence"].get(str(doc_id), [])
            labels = {item["label"] for item in annotations}
            if len(labels) > 1 or labels - set(LABELS[:2]):
                raise ValueError("Invalid gold labels")
            label = next(iter(labels)) if labels else "NEI"
            pair = (str(claim_id), str(doc_id))
            candidates.append((*pair, label))
            gold_by_pair[pair] = GoldCase(id=":".join(pair), label=label,
                                          rationales=[item["sentences"] for item in annotations])
    partitions = {}
    for name, quota in (("discovery", discovery_per_class), ("validation", validation_per_class)):
        partitions[name] = select_partition(candidates, quota, name, used_claims, used_documents)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "prior_inputs.jsonl").write_bytes(prior_bytes)
    source = {**SCIFACT_SOURCE, "name": "SciFact public train balanced client diagnostic", "split": "train",
              "sampling": {"seed": SEED, "selection_uses_gold_labels": True,
                           "selection": "seeded order within class quotas; unique claims and documents across partitions",
                           "prior_inputs_sha256": hashlib.sha256(prior_bytes).hexdigest(), "prior_pairs": len(previous)}}
    for name, rows in partitions.items():
        inputs = [InputCase(id=f"{cid}:{did}", claim_id=cid, doc_id=did,
                            claim=claims[int(cid)]["claim"], sentences=corpus[int(did)]["abstract"])
                  for cid, did, _ in rows]
        gold = [gold_by_pair[(cid, did)] for cid, did, _ in rows]
        _write_dataset(destination / name, inputs, gold, "scifact_cited_abstract_v1",
                       {**source, "partition": name, "class_counts": dict(Counter(row[2] for row in rows))})
    write_json(destination / "selection.json", {"source": source,
               "partitions": {name: {"pairs": len(rows), "manifest_sha256": sha256(destination / name / "manifest.json")}
                              for name, rows in partitions.items()}})
    print(f"Prepared {len(partitions['discovery'])} discovery and {len(partitions['validation'])} validation pairs. Gold labels not printed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--prior-inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--discovery-per-class", type=int, default=12)
    parser.add_argument("--validation-per-class", type=int, default=8)
    args = parser.parse_args()
    prepare(args.archive, args.prior_inputs, args.output, args.discovery_per_class, args.validation_per_class)
