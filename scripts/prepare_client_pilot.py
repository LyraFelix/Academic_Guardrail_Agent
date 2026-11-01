"""Select fixed public train pairs without using labels in sample selection.

This small interactive pilot is not an official test set or a bare-model ablation.
Run: python -m scripts.prepare_client_pilot --archive <official-tar> --output <new-dir>
"""

import argparse
import hashlib
import tarfile

from benchmarks.datasets import SCIFACT_SOURCE, _archive_records, _raw_index, _write_dataset, sha256
from benchmarks.schema import GoldCase, InputCase

SEED = "client-review-pilot-v1"


def prepare(archive_path, destination, size=12):
    if sha256(archive_path) != SCIFACT_SOURCE["sha256"]:
        raise ValueError("Official archive checksum mismatch")
    with tarfile.open(archive_path, "r:gz") as archive:
        corpus = _raw_index(_archive_records(archive, "data/corpus.jsonl"), "doc_id")
        claims = _raw_index(_archive_records(archive, "data/claims_train.jsonl"), "id")
    pairs = {(claim_id, doc_id) for claim_id, claim in claims.items() for doc_id in claim["cited_doc_ids"]}
    if not 1 <= size <= len(pairs):
        raise ValueError("Pilot size outside available pair count")
    selected = sorted(pairs, key=lambda pair: hashlib.sha256(f"{SEED}:{pair[0]}:{pair[1]}".encode()).hexdigest())[:size]
    inputs, gold = [], []
    for claim_id, doc_id in selected:
        claim, document = claims[claim_id], corpus[doc_id]
        identifier = f"{claim_id}:{doc_id}"
        inputs.append(InputCase(id=identifier, claim_id=str(claim_id), doc_id=str(doc_id),
                                claim=claim["claim"], sentences=document["abstract"]))
        annotations = claim["evidence"].get(str(doc_id), [])
        labels = {annotation["label"] for annotation in annotations}
        if len(labels) > 1 or labels - {"SUPPORT", "CONTRADICT"}:
            raise ValueError("Invalid pilot gold labels")
        gold.append(GoldCase(id=identifier, label=next(iter(labels)) if labels else "NEI",
                             rationales=[annotation["sentences"] for annotation in annotations]))
    source = {**SCIFACT_SOURCE, "name": "SciFact public train interactive pilot", "split": "train",
              "sampling": {"seed": SEED, "size": size, "population_pairs": len(pairs),
                           "selection": "lowest sha256(seed:claim_id:doc_id), independent of labels"}}
    _write_dataset(destination, inputs, gold, "scifact_cited_abstract_v1", source)
    print(f"Prepared {len(inputs)} label-separated pilot pairs at {destination}. Gold not printed.")


if __name__ == "__main__":
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, default=12)
    args = parser.parse_args()
    prepare(args.archive, args.output, args.size)
