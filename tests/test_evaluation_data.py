"""Preparation keeps the full denominator and gold outside predictor inputs."""

import hashlib
import io
import json
from pathlib import Path
import tarfile

import pytest

from benchmarks.datasets import load_gold, load_inputs, prepare_regression, prepare_scifact


def make_archive(path: Path, *, missing_document=False, conflicting=False):
    corpus = [{"doc_id": 10, "title": "A", "abstract": ["First sentence.", "Second sentence."]},
              {"doc_id": 20, "title": "B", "abstract": ["Other evidence."]}]
    if missing_document:
        corpus.pop()
    evidence = [{"label": "SUPPORT", "sentences": [1]}]
    if conflicting:
        evidence.append({"label": "CONTRADICT", "sentences": [0]})
    claims = [{"id": 1, "claim": "A claim.", "cited_doc_ids": [10, 20], "evidence": {"10": evidence}},
              {"id": 2, "claim": "Another claim.", "cited_doc_ids": [20], "evidence": {}}]
    with tarfile.open(path, "w:gz") as archive:
        for name, records in [("corpus", corpus), ("claims_dev", claims)]:
            data = "".join(json.dumps(row) + "\n" for row in records).encode()
            member = tarfile.TarInfo(f"data/{name}.jsonl")
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return {"name": "synthetic_schema_fixture", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def test_all_cited_documents_remain_including_unlabeled_negative(tmp_path):
    archive = tmp_path / "source.tar.gz"
    source = make_archive(archive)
    destination = tmp_path / "prepared"
    prepare_scifact(archive, destination, source=source)
    inputs, manifest = load_inputs(destination)
    labels = load_gold(destination)
    assert [row.id for row in inputs] == ["1:10", "1:20", "2:20"]
    assert [row.label for row in labels] == ["SUPPORT", "NEI", "NEI"]
    assert inputs[0].sentences == ["First sentence.", "Second sentence."]
    assert labels[0].rationales == [[1]]
    assert manifest["counts"]["claims"] == 2
    assert manifest["counts"]["pairs"] == 3
    assert "gold" not in (destination / "inputs.jsonl").read_text()
    assert "rationales" not in (destination / "inputs.jsonl").read_text()
    assert manifest["source"]["sha256"] == source["sha256"]


@pytest.mark.parametrize("problem", ["missing_document", "conflicting"])
def test_invalid_raw_annotations_fail_instead_of_skipping(tmp_path, problem):
    archive = tmp_path / "source.tar.gz"
    source = make_archive(archive, **{problem: True})
    with pytest.raises(ValueError):
        prepare_scifact(archive, tmp_path / "prepared", source=source)


def test_archive_checksum_is_enforced(tmp_path):
    archive = tmp_path / "source.tar.gz"
    source = make_archive(archive)
    source["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum"):
        prepare_scifact(archive, tmp_path / "prepared", source=source)


def test_changed_prepared_data_is_not_silently_reused(tmp_path):
    destination = tmp_path / "prepared"
    prepare_regression(destination)
    with (destination / "inputs.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{}\n')
    with pytest.raises(ValueError, match="checksum"):
        load_inputs(destination)


def test_preparation_refuses_existing_directory(tmp_path):
    destination = tmp_path / "prepared"
    prepare_regression(destination)
    original = (destination / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        prepare_regression(destination)
    assert (destination / "manifest.json").read_bytes() == original


def test_gold_is_not_part_of_the_predictor_schema():
    from benchmarks.schema import InputCase
    with pytest.raises(ValueError):
        InputCase(id="x", claim_id="1", doc_id="2", claim="C", sentences=["E"], gold="SUPPORT")
