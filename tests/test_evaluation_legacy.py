"""Archived inputs retain their bytes; old commands cannot silently run unsafe metrics."""

import hashlib
import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_historical_source_hashes_are_preserved():
    archive = ROOT / "benchmarks/legacy"
    manifest = json.loads((archive / "manifest.json").read_text())
    assert len(manifest["files"]) == 10
    for name, expected in manifest["files"].items():
        assert hashlib.sha256((archive / (name + ".txt")).read_bytes()).hexdigest() == expected


@pytest.mark.parametrize("name", ["benchmark_claims", "benchmark_scifact_official", "prepare_scifact_batches",
                                   "evaluate_llm_scifact_results", "benchmark_offline", "benchmark_baselines",
                                   "benchmark_runner", "benchmark_submodules_async", "synthetic_demo_benchmark"])
def test_legacy_import_is_inert_and_command_has_migration_message(name):
    module = importlib.import_module("benchmarks." + name)
    with pytest.raises(SystemExit, match="python -m benchmarks"):
        module.main()
