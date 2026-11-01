"""Persist predictions before scoring, and make every run independently auditable."""

from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
from unittest.mock import patch

from benchmarks.datasets import ROOT, load_gold, load_inputs, read_records, sha256, write_json
from benchmarks.metrics import score_predictions
from benchmarks.predictors import METHOD_CONFIGS, make_predictor
from benchmarks.reporting import write_reports
from benchmarks.schema import Prediction


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _code_record():
    files = sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "benchmarks").glob("*.py"))
    files.append(ROOT / "benchmarks/scifact_source.json")
    # Normalize CRLF so identical Git source on Windows and Unix compares equal.
    hashes = {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
              for path in files}
    def git(*arguments):
        completed = subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", "-C", str(ROOT), *arguments],
                                   capture_output=True, text=True, timeout=15)
        return completed.stdout.strip() if completed.returncode == 0 else None
    return {"git_commit": git("rev-parse", "HEAD"), "git_status": git("status", "--porcelain"),
            "normalized_source_sha256": _digest(hashes), "files": hashes}


@contextmanager
def offline_guard(attempts):
    """A swallowed exception must still leave an attempted-access record."""
    def forbidden(name):
        def stop(*args, **kwargs):
            attempts.append(name)
            raise RuntimeError(f"Offline evaluation boundary crossed: {name}")
        return stop
    with ExitStack() as stack:
        for name in ("socket.socket.connect", "socket.create_connection", "urllib.request.urlopen",
                     "httpx.AsyncClient.send", "httpx.Client.send",
                     "academic_guardrail.core.service.ChineseAcademicProvider",
                     "academic_guardrail.core.semantic_matcher.SemanticMatcher._get_model"):
            stack.enter_context(patch(name, side_effect=forbidden(name)))
        yield


def _semantic_digest(predictions):
    return _digest([row.model_dump(mode="json", exclude={"elapsed_ms"}) for row in predictions])


def _verify_snapshot(dataset, run_manifest, *, include_gold):
    path = dataset / "manifest.json"
    current = json.loads(path.read_text(encoding="utf-8"))
    if sha256(path) != run_manifest["dataset_manifest_sha256"] or current != run_manifest["dataset"]:
        raise ValueError("Dataset manifest changed during evaluation")
    names = ("inputs.jsonl", "gold.jsonl") if include_gold else ("inputs.jsonl",)
    for name in names:
        if sha256(dataset / name) != current["files"][name]:
            raise ValueError(f"Dataset file changed during evaluation: {name}")


def run_benchmark(dataset: Path, destination: Path, method="guardrail"):
    inputs, dataset_manifest = load_inputs(dataset)
    if method not in METHOD_CONFIGS:
        raise ValueError(f"Unknown method: {method}")
    destination.mkdir(parents=True, exist_ok=False)
    attempts, predictions = [], []
    manifest = {"schema_version": 1, "status": "incomplete", "method": method,
                "method_config": METHOD_CONFIGS[method], "dataset": dataset_manifest,
                "dataset_manifest_sha256": sha256(dataset / "manifest.json"),
                "started_utc": datetime.now(timezone.utc).isoformat(), "code": _code_record(),
                "environment": {"python": platform.python_version(), "platform": platform.system(),
                                "executable": sys.executable,
                                "packages": {name: version(name) for name in ("pydantic", "mcp", "httpx", "pypdf", "python-docx", "click", "rich")}},
                "offline_boundary_attempts": attempts, "processed": 0}
    write_json(destination / "manifest.json", manifest)
    try:
        _verify_snapshot(dataset, manifest, include_gold=False)
        with offline_guard(attempts), (destination / "predictions.jsonl").open("w", encoding="utf-8") as handle:
            predict = make_predictor(method)
            for item in inputs:
                started = time.perf_counter()
                try:
                    output = predict(item)
                    if output.id != item.id:
                        raise ValueError("Predictor returned a different input ID")
                except Exception as error:
                    output = Prediction(id=item.id, state="ERROR", error=f"{type(error).__name__}: {error}")
                output.elapsed_ms = round((time.perf_counter() - started) * 1000, 6)
                handle.write(output.model_dump_json() + "\n")
                handle.flush()
                predictions.append(output)
                manifest["processed"] = len(predictions)
        # Gold is first opened here, after all raw predictions are durable.
        _verify_snapshot(dataset, manifest, include_gold=True)
        gold = load_gold(dataset)
        metrics = score_predictions(dataset_manifest["protocol"], inputs, gold, predictions)
        _verify_snapshot(dataset, manifest, include_gold=True)
        write_json(destination / "metrics.json", metrics)
        write_reports(destination, metrics, inputs, gold, predictions)
        manifest.update({"status": "completed_with_errors" if metrics["errors"] or attempts else "completed",
                         "predictions_sha256": sha256(destination / "predictions.jsonl"),
                         "metrics_sha256": sha256(destination / "metrics.json"),
                         "semantic_outputs_sha256": _semantic_digest(predictions)})
        return metrics
    finally:
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(destination / "manifest.json", manifest)


def _read_run(directory):
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("status") not in {"completed", "completed_with_errors"}:
        raise ValueError("Run is incomplete or uses an unknown schema")
    for name in ("predictions", "metrics"):
        extension = "jsonl" if name == "predictions" else "json"
        if sha256(directory / f"{name}.{extension}") != manifest[f"{name}_sha256"]:
            raise ValueError(f"Run file checksum mismatch: {name}")
    predictions = read_records(directory / "predictions.jsonl", Prediction)
    if _semantic_digest(predictions) != manifest["semantic_outputs_sha256"]:
        raise ValueError("Semantic output checksum mismatch")
    return manifest, predictions


def rescore_run(dataset: Path, directory: Path):
    manifest, predictions = _read_run(directory)
    if sha256(dataset / "manifest.json") != manifest["dataset_manifest_sha256"]:
        raise ValueError("Prepared dataset differs from this run")
    inputs, dataset_manifest = load_inputs(dataset)
    metrics = score_predictions(dataset_manifest["protocol"], inputs, load_gold(dataset), predictions)
    saved = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
    if metrics != saved:
        raise ValueError("Replayed metrics differ from saved metrics")
    return metrics


def compare_runs(directories):
    if len(directories) < 2:
        raise ValueError("Comparison requires at least two runs")
    runs = [_read_run(directory)[0] for directory in directories]
    if len({run["dataset_manifest_sha256"] for run in runs}) != 1:
        raise ValueError("Cannot compare different dataset versions/protocols")
    same_method = len({_digest(run["method_config"]) for run in runs}) == 1
    same_code = len({run["code"]["normalized_source_sha256"] for run in runs}) == 1
    same_environment = len({_digest(run["environment"]) for run in runs}) == 1
    same_outputs = len({run["semantic_outputs_sha256"] for run in runs}) == 1
    return {"dataset_identical": True, "same_method": same_method, "same_code": same_code,
            "same_environment": same_environment, "same_semantic_outputs": same_outputs,
            "replay_verified": same_method and same_code and same_environment and same_outputs and
                               all(run["status"] == "completed" for run in runs),
            "runs": [{"path": str(path), "method": run["method"], "status": run["status"],
                      "metrics": json.loads((path / "metrics.json").read_text(encoding="utf-8"))}
                     for path, run in zip(directories, runs)]}
