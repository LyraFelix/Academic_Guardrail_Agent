"""Balanced diagnostic partitions must not leak repeated claims or sources."""

from collections import Counter
import hashlib
import io
import json
import tarfile

import pytest

from scripts.prepare_client_evaluation import select_partition


def candidates():
    return [(str(i), str(100 + i), label) for i, label in enumerate(
        ["SUPPORT", "CONTRADICT", "NEI"] * 8)]


def test_partitions_balance_classes_and_exclude_used_claims_and_documents():
    used_claims, used_documents = {"0"}, {"101"}
    first = select_partition(candidates(), 2, "discovery", used_claims, used_documents)
    second = select_partition(candidates(), 2, "validation", used_claims, used_documents)
    for rows in (first, second):
        assert Counter(row[2] for row in rows) == {"SUPPORT": 2, "CONTRADICT": 2, "NEI": 2}
    assert not {r[0] for r in first} & {r[0] for r in second}
    assert not {r[1] for r in first} & {r[1] for r in second}
    assert "0" not in {r[0] for r in first + second}
    assert "101" not in {r[1] for r in first + second}
    assert select_partition(candidates()[::-1], 2, "discovery", {"0"}, {"101"}) == first


def test_multiple_pairs_for_one_claim_or_document_cannot_fill_the_quota():
    duplicate_claims = [("same", str(i), label) for i, label in enumerate(["SUPPORT", "CONTRADICT", "NEI"])]
    duplicate_documents = [(str(i), "same", label) for i, label in enumerate(["SUPPORT", "CONTRADICT", "NEI"])]
    for rows in (duplicate_claims, duplicate_documents):
        with pytest.raises(ValueError, match="quota"):
            select_partition(rows, 1, "discovery", set(), set())


def test_preparation_binds_exclusions_to_the_bytes_actually_read(tmp_path, monkeypatch):
    from scripts import prepare_client_evaluation as sampler
    from benchmarks.schema import InputCase

    archive = tmp_path / "source.tar.gz"
    claims, corpus = [], []
    for i in range(12):
        label = ("SUPPORT", "CONTRADICT", "NEI")[i % 3]
        claims.append({"id": i, "claim": f"Claim {i}", "cited_doc_ids": [100 + i],
                       "evidence": {} if label == "NEI" else {str(100 + i): [{"label": label, "sentences": [0]}]}})
        corpus.append({"doc_id": 100 + i, "abstract": [f"Text {i}."]})
    with tarfile.open(archive, "w:gz") as handle:
        for name, rows in (("data/claims_train.jsonl", claims), ("data/corpus.jsonl", corpus)):
            data = "\n".join(json.dumps(row) for row in rows).encode()
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            handle.addfile(entry, io.BytesIO(data))
    monkeypatch.setattr(sampler, "SCIFACT_SOURCE", {"sha256": hashlib.sha256(archive.read_bytes()).hexdigest()})
    previous = tmp_path / "prior.jsonl"
    original = InputCase(id="0:100", claim_id="0", doc_id="100", claim="Claim 0", sentences=["Text 0."]).model_dump_json().encode()
    previous.write_bytes(original)
    selection = sampler.select_partition

    def change_file_after_parse(*args):
        previous.write_text(InputCase(id="1:101", claim_id="1", doc_id="101", claim="Claim 1", sentences=["Text 1."]).model_dump_json(), encoding="utf-8")
        return selection(*args)

    monkeypatch.setattr(sampler, "select_partition", change_file_after_parse)
    output = tmp_path / "prepared"
    sampler.prepare(archive, previous, output, 1, 1)
    manifest = json.loads((output / "discovery/manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"]["sampling"]["prior_inputs_sha256"] == hashlib.sha256(original).hexdigest()
    assert (output / "prior_inputs.jsonl").read_bytes() == original
