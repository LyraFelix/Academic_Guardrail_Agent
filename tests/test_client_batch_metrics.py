"""Client conclusions use fact labels; abstentions/errors still occupy rows."""

import json

import pytest

from benchmarks.datasets import sha256, write_json, write_records
from benchmarks.schema import GoldCase, InputCase
from scripts.client_review_batch import score


def setup_records(tmp_path):
    batch, submission = tmp_path / "batch", tmp_path / "submission"
    batch.mkdir()
    submission.mkdir()
    inputs = [InputCase(id=str(i), claim_id=str(i), doc_id="1", claim="Claim", sentences=["Text."]) for i in range(3)]
    write_records(batch / "inputs.jsonl", inputs)
    (batch / "packets.jsonl").write_text("\n".join(json.dumps({"id": str(i)}) for i in range(3)), encoding="utf-8")
    write_json(batch / "manifest.json", {"status": "completed", "inputs_sha256": sha256(batch / "inputs.jsonl"),
                                        "packets_sha256": sha256(batch / "packets.jsonl")})
    rows = [
        {"id": "0", "record": {"judgment": {"conclusion": "SUPPORTED"}}, "error": None},
        {"id": "1", "record": {"judgment": {"conclusion": "UNCERTAIN"}}, "error": None},
        {"id": "2", "record": None, "error": "Quote rejected"},
    ]
    (submission / "predictions.jsonl").write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    (submission / "judgments.jsonl").write_text("{}\n", encoding="utf-8")
    write_json(submission / "manifest.json", {"status": "completed_with_errors",
               "batch_manifest_sha256": sha256(batch / "manifest.json"),
               "predictions_sha256": sha256(submission / "predictions.jsonl"),
               "judgments_sha256": sha256(submission / "judgments.jsonl")})
    gold = tmp_path / "gold.jsonl"
    write_records(gold, [GoldCase(id=str(i), label=label) for i, label in enumerate(("SUPPORT", "CONTRADICT", "NEI"))])
    return batch, submission, gold


def test_client_metrics_keep_abstentions_and_errors_in_denominator(tmp_path):
    batch, submission, gold = setup_records(tmp_path)
    result = score(batch, submission, gold, tmp_path / "metrics.json")
    assert result["total"] == 3 and result["errors"] == 1
    assert result["label_agreement"] == {"numerator": 1, "denominator": 3, "value": 1 / 3}
    assert result["resolved_rate"]["numerator"] == 1
    assert result["agreement_on_resolved"]["denominator"] == 1
    assert result["state_by_gold"]["CONTRADICT"]["ABSTAIN"] == 1


def test_changed_client_predictions_are_rejected(tmp_path):
    batch, submission, gold = setup_records(tmp_path)
    with (submission / "predictions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    with pytest.raises(ValueError, match="checksum"):
        score(batch, submission, gold, tmp_path / "metrics.json")
