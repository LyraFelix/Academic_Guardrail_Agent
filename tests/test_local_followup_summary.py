"""Synthetic offline checks for pooling frozen runs without hiding failed cases."""

import csv
import importlib
import json

import pytest

from tests.test_local_followup_evaluation import fake_model, freeze, install_local_transport, make_material, modules


def summary_module():
    return importlib.import_module("scripts.summarize_local_followup_evaluation")


def selection_plan(identifier, partition, paper_id):
    return {"protocol": "local_evidence_followup_v2", "model": "gpt-6.1-terra", "reasoning": "max",
            "partition": partition, "source_sha256": {f"/{paper_id}.txt": paper_id},
            "cases": [{"id": identifier, "input": {"paper_id": paper_id, "source_path": f"/{paper_id}.txt"}}]}


@pytest.mark.parametrize("change", ["protocol", "model", "reasoning", "overlap", "paper", "source_alias"])
def test_summary_rejects_incompatible_or_leaking_batches(change):
    first = selection_plan("case_a", "development", "paper_a")
    second = selection_plan("case_b", "validation", "paper_b")
    if change in {"protocol", "model", "reasoning"}:
        second[change] = "different"
    elif change == "overlap":
        second["cases"][0]["id"] = "case_a"
    elif change == "paper":
        second["cases"][0]["input"]["paper_id"] = "paper_a"
    else:
        second["source_sha256"]["/paper_b.txt"] = "paper_a"
    with pytest.raises(ValueError):
        summary_module().validate_batch_selection([first, second])


@pytest.mark.asyncio
async def test_three_batches_recompute_primary_secondary_metrics_and_actual_cost(tmp_path, monkeypatch):
    _, prep, runner, _ = modules()
    install_local_transport(monkeypatch, prep, runner)
    batches = []
    specifications = [
        ("CONTRADICTED", {"initial": "NEI", "fulltext_single": "CONTRADICTED", "fulltext_direct": "CONTRADICTED"}),
        ("SUPPORTED", {"initial": "NEI", "fulltext_single": "NEI", "fulltext_direct": "FAIL"}),
        ("NOT_ENOUGH_EVIDENCE", {"initial": "NO_GAP", "fulltext_single": "CONTRADICTED"}),
    ]
    for index, (label, decisions) in enumerate(specifications):
        root = tmp_path / f"batch_{index}"
        root.mkdir()
        material = make_material(root, identifier=f"case_{index}", partition=f"partition_{index}",
                                 paper_id=f"paper_{index}", fulltext_label=label)
        # Separate synthetic source bytes, like the distinct papers in real batches.
        with material["source"].open("a", encoding="utf-8") as handle:
            handle.write(f"\nSource fixture {index}.\n")
        plan = await freeze(material, prep)
        fake_model(monkeypatch, runner, decisions, missing_usage=index == 2)
        run = root / "run"
        await runner.run_async(plan, run)
        batches.append((run, material["gold"]))
    output, case_csv = tmp_path / "summary.json", tmp_path / "cases.csv"
    result = summary_module().summarize(batches, output, case_csv)
    assert result["cases"] == 3 and len(result["batches"]) == 3
    assert result["max_actual_cli_calls"] == 12
    assert result["actual_cost"]["model_calls"] == 11
    assert result["shared_initial_cost"]["model_calls"] == 3
    assert result["arms"]["fulltext_single"]["cost"]["model_calls"] == 3
    assert result["arms"]["fulltext_direct"]["cost"]["model_calls"] == 6
    assert result["arms"]["local_followup"]["cost"]["model_calls"] == 5
    assert result["actual_cost"]["reported_tokens"]["input_tokens"] is None
    assert result["actual_cost"]["partial_token_subtotals"]["input_tokens"] == 800
    assert result["paired_primary"]["right_wins"] == ["case_1", "case_2"]
    assert result["paired_primary"]["right_losses"] == ["case_0"]
    assert result["paired_secondary"]["left"] == "fulltext_direct"
    single = result["arms"]["fulltext_single"]
    assert single["refutation"]["precision"]["count"] == 1
    assert single["refutation"]["precision"]["denominator"] == 2
    assert single["refutation"]["recall"]["denominator"] == 1
    assert single["refutation"]["recall"]["interval"]["lower"] < 1
    assert single["avoidable_nei"]["count"] == 1
    assert single["avoidable_nei"]["denominator"] == 2
    assert result["arms"]["fulltext_direct"]["outcome_rates"]["ERROR"]["denominator"] == 3
    assert result["arms"]["local_followup"]["false_concrete"]["count"] == 1
    assert len(result["per_paper"]) == 3
    assert result["per_paper"][0]["arms"]["fulltext_single"]["refutation"]["recall"]["denominator"] == 1
    with case_csv.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 3 and rows[0]["id"] == "case_0"
    assert rows[2]["local_followup"] == "NEI"
    assert json.loads(output.read_bytes())["actual_cost"] == result["actual_cost"]


@pytest.mark.asyncio
async def test_summary_revalidates_run_before_reading_gold(tmp_path, monkeypatch):
    helper, prep, runner, _ = modules()
    install_local_transport(monkeypatch, prep, runner)
    material = make_material(tmp_path)
    plan = await freeze(material, prep)
    fake_model(monkeypatch, runner, {"initial": "NEI"})
    run = tmp_path / "run"
    await runner.run_async(plan, run)
    rows = json.loads((run / "rows.json").read_bytes())
    (run / "rows.json").write_text(json.dumps(rows[:-1]), encoding="utf-8")
    manifest = json.loads((run / "manifest.json").read_bytes())
    manifest["files"] = helper.file_hashes(run)
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    module = summary_module()

    def reject_gold(*args):
        pytest.fail("An invalid run must be rejected before opening any gold")

    monkeypatch.setattr(module, "read_gold", reject_gold)
    with pytest.raises(ValueError, match="exactly|cover"):
        module.summarize([(run, material["gold"])], tmp_path / "summary.json", tmp_path / "cases.csv")
