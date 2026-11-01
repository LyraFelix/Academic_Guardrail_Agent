"""Replay, failures, input visibility and offline execution are observable contracts."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from benchmarks.datasets import prepare_regression
from benchmarks.predictors import sentence_ids_for_excerpt
from benchmarks.runner import compare_runs, rescore_run, run_benchmark


def test_full_run_and_scoring_replay_are_deterministic(tmp_path):
    dataset = tmp_path / "dataset"
    prepare_regression(dataset)
    first, second = tmp_path / "first", tmp_path / "second"
    result = run_benchmark(dataset, first)
    repeated = run_benchmark(dataset, second)
    assert result["case_pass"]["numerator"] == result["total"] == 50
    assert result == repeated == rescore_run(dataset, first)
    compared = compare_runs([first, second])
    assert compared["same_semantic_outputs"] is True
    assert compared["replay_verified"] is True
    manifest = json.loads((first / "manifest.json").read_text())
    assert manifest["status"] == "completed"
    assert manifest["offline_boundary_attempts"] == []
    assert manifest["method_config"]["embeddings"] is False
    assert (first / "cases.tsv").is_file() and (first / "summary.md").is_file()
    with pytest.raises(FileExistsError):
        run_benchmark(dataset, first)


def test_predictor_errors_remain_in_denominator(tmp_path, monkeypatch):
    dataset, run = tmp_path / "dataset", tmp_path / "run"
    prepare_regression(dataset)

    def fail(case):
        assert "expected_state" not in case.model_dump() and "label" not in case.model_dump()
        raise RuntimeError("deliberate test failure")

    monkeypatch.setattr("benchmarks.runner.make_predictor", lambda method: fail)
    result = run_benchmark(dataset, run)
    assert result["errors"] == result["total"] == 50
    assert result["case_pass"]["numerator"] == 0
    assert json.loads((run / "manifest.json").read_text())["status"] == "completed_with_errors"
    assert len((run / "predictions.jsonl").read_text().splitlines()) == 50


def test_gold_load_occurs_only_after_predictions_written(tmp_path, monkeypatch):
    import benchmarks.runner as runner
    dataset, run = tmp_path / "dataset", tmp_path / "run"
    prepare_regression(dataset)
    original = runner.load_gold

    def check(directory):
        assert len((run / "predictions.jsonl").read_text(encoding="utf-8").splitlines()) == 50
        return original(directory)

    monkeypatch.setattr(runner, "load_gold", check)
    run_benchmark(dataset, run)


def test_interrupt_keeps_partial_rows_and_manifest(tmp_path, monkeypatch):
    from benchmarks.schema import Prediction
    dataset, run = tmp_path / "dataset", tmp_path / "run"
    prepare_regression(dataset)
    calls = []

    def interrupted(case):
        calls.append(case.id)
        if len(calls) == 2:
            raise KeyboardInterrupt()
        return Prediction(id=case.id, state="REVIEW_REQUIRED")

    monkeypatch.setattr("benchmarks.runner.make_predictor", lambda method: interrupted)
    with pytest.raises(KeyboardInterrupt):
        run_benchmark(dataset, run)
    assert len((run / "predictions.jsonl").read_text().splitlines()) == 1
    assert json.loads((run / "manifest.json").read_text())["status"] == "incomplete"
    with pytest.raises(ValueError):
        rescore_run(dataset, run)


def test_modified_prediction_file_cannot_be_replayed(tmp_path):
    dataset, run = tmp_path / "dataset", tmp_path / "run"
    prepare_regression(dataset)
    run_benchmark(dataset, run, method="always_review")
    with (run / "predictions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{}\n')
    with pytest.raises(ValueError, match="checksum"):
        rescore_run(dataset, run)


def test_unreturned_sentence_cannot_be_counted_as_rationale():
    sentences = ["Treatment was tested.", "Treatment improves survival.", "Long follow-up is needed."]
    assert sentence_ids_for_excerpt(sentences, "improves survival") == [1]
    assert sentence_ids_for_excerpt(sentences, "") == []
    with pytest.raises(ValueError):
        sentence_ids_for_excerpt(sentences, "Invented evidence.")


def test_cli_never_downloads_missing_dataset(tmp_path):
    completed = subprocess.run([sys.executable, "-m", "benchmarks", "run", "--dataset", str(tmp_path / "missing"),
                                "--output", str(tmp_path / "run")], capture_output=True, text=True, encoding="utf-8")
    assert completed.returncode != 0
    assert "Traceback" not in completed.stderr
    assert not (tmp_path / "run").exists()


def test_offline_attempts_cannot_be_hidden_as_success(tmp_path, monkeypatch):
    import urllib.request
    from benchmarks.schema import Prediction
    dataset, run = tmp_path / "dataset", tmp_path / "run"
    prepare_regression(dataset)

    def swallowing(case):
        try:
            urllib.request.urlopen("https://invalid.example")
        except RuntimeError:
            pass
        return Prediction(id=case.id, state="REVIEW_REQUIRED")

    monkeypatch.setattr("benchmarks.runner.make_predictor", lambda method: swallowing)
    run_benchmark(dataset, run)
    manifest = json.loads((run / "manifest.json").read_text())
    assert manifest["status"] == "completed_with_errors"
    assert len(manifest["offline_boundary_attempts"]) == 50


def test_compare_rejects_different_dataset_manifest(tmp_path):
    from benchmarks.datasets import write_json
    dataset = tmp_path / "dataset"
    prepare_regression(dataset)
    first, second = tmp_path / "first", tmp_path / "second"
    run_benchmark(dataset, first, method="always_review")
    manifest = json.loads((dataset / "manifest.json").read_text())
    manifest["source"]["name"] = "different dataset revision"
    write_json(dataset / "manifest.json", manifest)
    run_benchmark(dataset, second, method="always_review")
    with pytest.raises(ValueError, match="different dataset"):
        compare_runs([first, second])


def test_dataset_change_during_prediction_cannot_complete(tmp_path, monkeypatch):
    from benchmarks.datasets import sha256, write_json
    from benchmarks.schema import Prediction
    dataset, run = tmp_path / "dataset", tmp_path / "run"
    prepare_regression(dataset)
    changed = []

    def mutate(case):
        if not changed:
            path = dataset / "gold.jsonl"
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            rows[0]["expected_state"] = "TEXT_ALIGNED"
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            manifest = json.loads((dataset / "manifest.json").read_text())
            manifest["files"]["gold.jsonl"] = sha256(path)
            write_json(dataset / "manifest.json", manifest)
            changed.append(True)
        return Prediction(id=case.id, state="REVIEW_REQUIRED")

    monkeypatch.setattr("benchmarks.runner.make_predictor", lambda method: mutate)
    with pytest.raises(ValueError, match="changed during"):
        run_benchmark(dataset, run)
    assert json.loads((run / "manifest.json").read_text())["status"] == "incomplete"
    assert len((run / "predictions.jsonl").read_text().splitlines()) == 50
