"""Check fair inputs and complete paired denominators with hand-computed examples."""

import json

import pytest

from benchmarks.client_comparison import ARMS, arm_metrics, make_prompt, paired_metrics, raw_prediction, wilson_interval
from scripts.codex_review_client import command_for, parse_events, strict_schema
from scripts.run_paired_review import inspect_answer, load_frozen_packet
from academic_guardrail.core.review_store import ReviewStore, content_digest
from tests.test_claim_review import judgment, packet


def row(identifier, prediction, error=None):
    return {"id": identifier, "prediction": prediction, "validation_error": error,
            "quotes_valid": True, "quote_count": 1, "exact_quote_count": 1,
            "usage": None, "elapsed_seconds": 1.0}


def test_three_arms_share_evidence_and_guided_difference_is_only_hints():
    value = packet().model_dump(mode="json")
    value["rule_summary"] = value.pop("rule_assessment")
    prompts = {arm: make_prompt(value, arm) for arm in ARMS}
    sources = [text.split("SOURCE_DATA_JSON\n")[1].split("\n\nMCP_HINTS_JSON")[0] for text in prompts.values()]
    assert len(set(sources)) == 1
    assert prompts["mcp"].startswith(prompts["guided_direct"] + "\n\nMCP_HINTS_JSON")
    assert "record_claim_review" not in prompts["guided_direct"]
    assert "gold" not in json.loads(sources[0])


def test_invalid_quote_does_not_remove_a_raw_semantic_error():
    value = packet()
    answer = judgment(value, conclusion="CONTRADICTED", quotes=[{"evidence_id": "e1", "quote": "Invented text."}]).model_dump()
    receipt = {"error": None, "response": answer, "elapsed_seconds": 1, "usage": None}
    inspected = inspect_answer(value, receipt)
    assert inspected["prediction"] == "CONTRADICT"
    assert inspected["validation_error"] is not None
    metrics = arm_metrics([{**inspected, "id": "a"}], {"a": "SUPPORT"})
    assert metrics["raw_accuracy"]["numerator"] == 0
    assert metrics["raw_accuracy"]["denominator"] == 1
    assert metrics["accepted_accuracy"]["denominator"] == 0


def test_raw_label_survives_invalid_judgment_schema_but_not_missing_json():
    assert raw_prediction({"response": {"conclusion": "CONTRADICTED"}}) == "CONTRADICT"
    for value in (None, [], {"conclusion": {}}, {"conclusion": "unknown"}):
        assert raw_prediction({"response": value}) == "ERROR"
    assert raw_prediction({"response": {"conclusion": "SUPPORTED"}, "error": "timeout"}) == "ERROR"


def test_paired_wins_losses_and_error_denominators():
    gold = {"a": "CONTRADICT", "b": "CONTRADICT", "c": "SUPPORT", "d": "NEI"}
    left = [row("a", "NEI"), row("b", "CONTRADICT"), row("c", "SUPPORT"), row("d", "ERROR", "timeout")]
    right = [row("a", "CONTRADICT"), row("b", "NEI"), row("c", "SUPPORT"), row("d", "NEI")]
    paired = paired_metrics(left, right, gold)
    assert paired["right_wins"] == ["a", "d"]
    assert paired["right_losses"] == ["b"]
    assert paired["ties"] == 1
    assert paired["accuracy_difference"] == 0.25
    assert paired["exact_mcnemar_two_sided_p"] == 1.0
    metrics = arm_metrics(left, gold)
    assert metrics["class_metrics"]["CONTRADICT"]["recall"]["denominator"] == 2
    assert metrics["errors"] == 1
    with pytest.raises(ValueError):
        paired_metrics(left[:-1], right, gold)


def test_schema_and_cli_have_equal_fixed_settings_and_no_resume():
    schema = strict_schema({"type": "object", "properties": {"optional": {"type": "string", "default": ""}}})
    assert schema["required"] == ["optional"]
    assert "default" not in schema["properties"]["optional"]
    command = command_for("codex", "schema.json", "answer.json")
    for argument in ("--ephemeral", "--ignore-user-config", "read-only", "project_doc_max_bytes=0",
                     "memories.use_memories=false", 'web_search="disabled"'):
        assert argument in command
    assert "resume" not in command


def test_cli_records_usage_and_detects_tool_use_and_failed_turns():
    events = [{"type": "thread.started", "thread_id": "new"},
              {"type": "item.completed", "item": {"type": "command_execution", "command": "bad"}},
              {"type": "turn.completed", "usage": {"input_tokens": 12, "output_tokens": 3}}]
    result = parse_events("\n".join(map(json.dumps, events)))
    assert result["tool_items"] == ["command_execution"]
    assert result["usage"]["input_tokens"] == 12
    assert parse_events('{"type":"turn.failed"}')["failed_turns"] == 1
    assert wilson_interval(0, 0) is None
    assert 0 < wilson_interval(3, 10)["lower"] < 0.3 < wilson_interval(3, 10)["upper"] < 1


def test_started_tool_is_rejected_even_without_completion():
    events = [{"type": "item.started", "item": {"type": "mcp_tool_call"}},
              {"type": "turn.completed", "usage": {"input_tokens": 1}}]
    assert parse_events("\n".join(map(json.dumps, events)))["tool_items"] == ["mcp_tool_call"]


def test_missing_token_field_stays_unknown():
    observed = row("a", "SUPPORT")
    observed["usage"] = {"input_tokens": 100, "output_tokens": 12}
    result = arm_metrics([observed], {"a": "SUPPORT"})
    assert result["reported_tokens"]["input_tokens"] == 100
    assert result["reported_tokens"]["reasoning_output_tokens"] is None
    assert result["token_reporting_cases"]["reasoning_output_tokens"] == 0


def test_common_checker_binds_the_stored_packet_to_original_digest(tmp_path):
    value = packet()
    store = ReviewStore(tmp_path / "stored")
    digest = store.save_packet(value)
    view = {"packet_id": value.packet_id, "packet_sha256": digest}
    assert load_frozen_packet(tmp_path, view) == value
    path = tmp_path / "stored" / f"{value.packet_id}.packet.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["packet"]["claim"] = "A replaced claim."
    data["sha256"] = content_digest(data["packet"])
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen"):
        load_frozen_packet(tmp_path, view)


def test_one_tool_violation_stops_before_the_next_batch(tmp_path, monkeypatch):
    from scripts import run_paired_review as runner
    from types import SimpleNamespace

    value = packet()
    schedule = [{"id": name, "arm": arm} for name in ("a", "b") for arm in ARMS]
    plan = {"model": "gpt-6.1-sol", "reasoning": "high", "schedule": schedule}
    views = [{"id": name, "packet_id": value.packet_id} for name in ("a", "b")]
    monkeypatch.setattr(runner, "load_plan", lambda *args: (plan, json.dumps(plan).encode(), views, ["text"] * 6, {}))
    monkeypatch.setattr(runner, "load_frozen_packet", lambda *args: value)
    monkeypatch.setattr(runner, "_code_record", lambda: {"test": True})
    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout="test CLI"))
    calls = []

    def fake_invoke(prompt, schema, destination, timeout):
        calls.append(destination.name)
        return {"error": "unexpected_tool_use" if destination.name == "attempt_000" else None,
                "response": judgment(value).model_dump(), "elapsed_seconds": 1, "usage": None}

    monkeypatch.setattr(runner, "invoke", fake_invoke)
    with pytest.raises(RuntimeError, match="Isolation"):
        runner.run(tmp_path / "plan.json", tmp_path / "batch", tmp_path / "run")
    assert sorted(calls) == ["attempt_000", "attempt_001", "attempt_002"]
    manifest = json.loads((tmp_path / "run/manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "incomplete"
    assert manifest["attempted"] == 3


def test_real_plan_roundtrip_preserves_prompt_bytes_on_windows(tmp_path):
    from benchmarks.datasets import sha256, write_json
    from benchmarks.schema import InputCase
    from scripts.prepare_paired_review import freeze_plan
    from scripts.run_paired_review import load_plan

    batch = tmp_path / "batch"
    batch.mkdir()
    value = packet()
    digest = ReviewStore(batch / "stored").save_packet(value)
    source = InputCase(id="case", claim_id="1", doc_id="2", claim=value.claim,
                       sentences=[item.text for item in value.evidence])
    (batch / "inputs.jsonl").write_bytes((source.model_dump_json() + "\n").encode())
    view = value.model_dump(mode="json")
    view.update(id="case", packet_sha256=digest, rule_summary=view.pop("rule_assessment"))
    (batch / "packets.jsonl").write_bytes((json.dumps(view) + "\n").encode())
    write_json(batch / "manifest.json", {"status": "completed", "inputs_sha256": sha256(batch / "inputs.jsonl"),
                                        "packets_sha256": sha256(batch / "packets.jsonl"), "expected_gold_sha256": "0" * 64})
    plan_dir = tmp_path / "plan"
    freeze_plan(batch, plan_dir)
    plan, _, _, prompts, _ = load_plan(plan_dir / "plan.json", batch)
    assert len(prompts) == 3
    for item, prompt in zip(plan["schedule"], prompts):
        assert (plan_dir / item["prompt_file"]).read_bytes() == prompt.encode("utf-8")
        assert "\r\n" not in prompt
    (plan_dir / plan["schedule"][0]["prompt_file"]).write_bytes(b"Changed prompt")
    with pytest.raises(ValueError, match="Prompt changed"):
        load_plan(plan_dir / "plan.json", batch)
