"""Offline protocol tests: real storage/retrieval, fake transport and model receipts."""

from contextlib import asynccontextmanager
import hashlib
import importlib
import json
from pathlib import Path
import shutil

import pytest


def modules():
    return tuple(importlib.import_module(name) for name in (
        "benchmarks.local_followup_evaluation", "scripts.prepare_local_followup_evaluation",
        "scripts.run_local_followup_evaluation", "scripts.score_local_followup_evaluation"))


@pytest.fixture
def material(tmp_path):
    refs = tmp_path / "refs"
    refs.mkdir()
    source = refs / "study.txt"
    fixture = Path(__file__).resolve().parents[1] / "docs/examples/local_followup_refs/study.txt"
    shutil.copyfile(fixture, source)
    observations = "\n\n".join(f"Additional observation {index} discusses study limitations." for index in range(40))
    source.write_text(source.read_text(encoding="utf-8").replace("\nReferences\n", f"\n{observations}\n\nReferences\n"),
                      encoding="utf-8")
    item = {"id": "dev_001", "partition": "dev", "paper_id": "synthetic",
            "claim": "The treatment reduced mortality by 25% at six months.",
            "citation_str_or_doi": "Synthetic Local Follow-up Study",
            "paper_title": "Synthetic Local Follow-up Study", "source_path": str(source)}
    inputs = tmp_path / "inputs.jsonl"
    inputs.write_text(json.dumps(item) + "\n", encoding="utf-8")
    gold_bytes = (json.dumps({"id": item["id"], "fulltext_label": "SUPPORTED",
                              "abstract_only_label": "NOT_ENOUGH_EVIDENCE"}) + "\n").encode()
    gold = tmp_path / "gold.jsonl"
    gold.write_bytes(gold_bytes)
    return {"inputs": inputs, "refs": refs, "source": source, "gold": gold,
            "gold_hash": hashlib.sha256(gold_bytes).hexdigest(), "root": tmp_path}


def install_local_transport(monkeypatch, prep, runner):
    """Only replace the wire; exercise production preparation, lookup and records."""
    from academic_guardrail.core.claim_review import evidence_page, packet_response
    from academic_guardrail.core.followup_report import save_review_report
    from academic_guardrail.core.local_review import follow_up_review, prepare_local_review
    from academic_guardrail.core.review_models import ClientJudgment
    from academic_guardrail.core.review_store import ReviewStore, content_digest

    @asynccontextmanager
    async def server(batch, output):
        yield ReviewStore(batch / "stored")
        (output / "boundary_attempts.json").write_text("[]", encoding="utf-8")

    async def call(store, name, arguments, log):
        if name == "prepare_local_claim_review":
            packet = await prepare_local_review(**arguments, store=store)
            result = {**packet_response(packet, content_digest(packet.model_dump(mode="json"))),
                      "local_review": store.load_context(packet.packet_id).model_dump(mode="json")}
        elif name == "read_claim_evidence":
            packet = store.load_packet(arguments["packet_id"])
            result = {**evidence_page(packet, arguments["offset"]),
                      "packet_sha256": content_digest(packet.model_dump(mode="json"))}
        elif name == "record_claim_review":
            result = store.record(arguments["packet_id"], ClientJudgment.model_validate(arguments["judgment"]),
                                  arguments["expected_packet_sha256"])
        elif name == "follow_up_local_claim":
            packet = follow_up_review(**arguments, store=store)
            result = {**packet_response(packet, content_digest(packet.model_dump(mode="json"))),
                      "local_review": store.load_context(packet.packet_id).model_dump(mode="json")}
        elif name == "generate_claim_review_report":
            result = save_review_report(store, **arguments)
        else:
            raise AssertionError(name)
        log.write(json.dumps({"tool": name, "arguments": arguments, "response": result}) + "\n")
        log.flush()
        return result

    for module in (prep, runner):
        monkeypatch.setattr(module, "server", server)
        monkeypatch.setattr(module, "call", call)
    monkeypatch.setattr(importlib.import_module("scripts.validate_local_followup"), "call", call)
    monkeypatch.setattr(runner, "cli_version", lambda: "offline fixture")


def fake_model(monkeypatch, runner, decisions, *, missing_usage=False):
    """Return immutable raw responses whose semantics are controlled by each test."""
    calls = []

    def invoke(prompt, schema, destination, timeout):
        from scripts.codex_review_client import MODEL, REASONING
        from scripts.validate_local_followup import fixture_judgment
        destination.mkdir(parents=True)
        data = json.loads(prompt.split("SOURCE_DATA_JSON\n", 1)[1].split("\n\nPRIOR_JUDGMENT_JSON", 1)[0])
        stage = destination.name.split("_", 2)[-1]
        choice = decisions.get(stage, "SUPPORTED")
        response = fixture_judgment(data, final=choice not in {"NEI", "NO_GAP", "BAD_GAP", "TOOLS", "DECISIVE"})
        response["client_model"] = MODEL
        response.update(suggested_revision=None, findings=[])
        if choice == "CONTRADICTED":
            response["conclusion"] = "CONTRADICTED"
        if choice == "DECISIVE":
            response.update(conclusion="SUPPORTED", missing_evidence=[],
                            quotes=[{"evidence_id": data["evidence"][0]["id"], "quote": data["evidence"][0]["text"]}])
        if choice == "BAD_QUOTE":
            response["quotes"][0]["quote"] = "not an exact source quotation"
        if choice == "NO_GAP":
            response["missing_evidence"] = []
        if choice == "BAD_GAP":
            response["missing_evidence"][0]["claim_part"] = "absent claim substring"
        receipt = {"requested_model": MODEL, "reasoning": REASONING, "elapsed_seconds": 0.5,
                   "returncode": 0, "error": None, "event_stream_valid": True, "response": response,
                   "thread_ids": [f"thread-{destination.name}"], "completed_turns": 1,
                   "tool_items": [], "failed_turns": 0, "warnings": [],
                   "usage": None if missing_usage else {"input_tokens": 100, "cached_input_tokens": 0,
                                                         "output_tokens": 20}}
        if choice == "FAIL":
            receipt.update(error="cli_or_turn_failure", response=None)
        if choice == "TOOLS":
            receipt.update(error="cli_or_turn_failure", tool_items=["command_execution"])
        if choice == "DUPLICATE_THREAD":
            receipt["thread_ids"] = ["thread-attempt_000_initial"]
        calls.append((stage, receipt))
        for name, value in (("receipt.json", receipt), ("response.json", response),
                            ("command.json", ["fake-model-no-external-call"])):
            (destination / name).write_text(json.dumps(value), encoding="utf-8")
        (destination / "events.jsonl").write_text("{}\n", encoding="utf-8")
        (destination / "stderr.txt").write_text("", encoding="utf-8")
        (destination / "prompt.txt").write_bytes(prompt.encode("utf-8"))
        return receipt

    monkeypatch.setattr(runner, "invoke", invoke)
    return calls


async def freeze(material, prep):
    output = material["root"] / "prepared"
    await prep.prepare(material["inputs"], material["refs"], output, material["gold_hash"])
    return output / "plan.json"


@pytest.mark.asyncio
async def test_prepare_reads_all_pages_and_never_opens_gold(material, monkeypatch):
    helper, prep, runner, _ = modules()
    install_local_transport(monkeypatch, prep, runner)
    original_open = Path.open

    def no_gold(path, *args, **kwargs):
        assert path.resolve() != material["gold"].resolve(), "gold was opened before scoring"
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", no_gold)
    plan_path = await freeze(material, prep)
    plan, _, _ = helper.load_plan(plan_path)
    case = plan["cases"][0]
    full = helper.load_packet_view(plan_path.parent, case["full_text_packet"])
    assert len(full["evidence"]) > 24
    assert len(full["evidence"]) == full["total_evidence"]
    assert full["local_review"]["source"]["path"] == str(material["source"].resolve())
    assert not list(plan_path.parent.glob("*gold*"))


@pytest.mark.asyncio
async def test_packet_view_cannot_change_the_claim_given_to_the_model(material, monkeypatch):
    helper, prep, runner, _ = modules()
    install_local_transport(monkeypatch, prep, runner)
    plan_path = await freeze(material, prep)
    plan, _, _ = helper.load_plan(plan_path)
    case = plan["cases"][0]
    packet = helper.load_packet_view(plan_path.parent, case["abstract_packet"])
    packet["claim"] = "A substituted question is not the frozen claim."
    with pytest.raises(ValueError, match="claim"):
        helper.check_packet(plan_path.parent, packet, case["input"], "abstract")


@pytest.mark.asyncio
async def test_case_identifier_cannot_differ_from_its_frozen_input(material, monkeypatch):
    helper, prep, runner, _ = modules()
    install_local_transport(monkeypatch, prep, runner)
    path = await freeze(material, prep)
    plan = json.loads(path.read_bytes())
    plan["cases"][0]["id"] = "different_gold_identifier"
    path.write_text(json.dumps(plan), encoding="utf-8")
    manifest = json.loads((path.parent / "manifest.json").read_bytes())
    manifest["files"] = helper.file_hashes(path.parent)
    (path.parent / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="ID|identifier"):
        helper.load_plan(path)


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["source", "plan", "schema", "code"])
async def test_changed_freeze_prevents_any_model_call(material, monkeypatch, changed):
    helper, prep, runner, _ = modules()
    install_local_transport(monkeypatch, prep, runner)
    plan = await freeze(material, prep)
    calls = fake_model(monkeypatch, runner, {"initial": "NEI"})
    if changed == "code":
        monkeypatch.setattr(helper, "runtime_code_hashes", lambda: {"changed": "0" * 64})
    else:
        path = material["source"] if changed == "source" else plan if changed == "plan" else plan.parent / "schema.json"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(" ")
    with pytest.raises(ValueError, match="changed|differs|checksum"):
        await runner.run_async(plan, material["root"] / "run")
    assert calls == []


@pytest.mark.asyncio
async def test_full_workflow_preserves_prepared_store_and_accounts_shared_cost(material, monkeypatch):
    helper, prep, runner, scorer = modules()
    install_local_transport(monkeypatch, prep, runner)
    plan = await freeze(material, prep)
    before = helper.file_hashes(plan.parent)
    calls = fake_model(monkeypatch, runner, {"initial": "NEI"})
    run = material["root"] / "run"
    original_open = Path.open
    with monkeypatch.context() as guard:
        def no_gold(path, *args, **kwargs):
            assert path.resolve() != material["gold"].resolve(), "runner opened gold"
            return original_open(path, *args, **kwargs)
        guard.setattr(Path, "open", no_gold)
        manifest = await runner.run_async(plan, run)
    assert manifest["status"] == "completed"
    assert manifest["actual_cli_calls"] == len(calls) == 3
    assert helper.file_hashes(plan.parent) == before
    for line in (run / "requests.jsonl").read_text().splitlines():
        request = json.loads(line)
        assert (run / request["prompt_file"]).read_bytes() == (run / request["attempt"] / "prompt.txt").read_bytes()
    report = scorer.score(run, material["gold"], material["root"] / "score.json")
    assert report["actual_cost"]["model_calls"] == 3
    assert report["arms"]["local_followup"]["cost"]["model_calls"] == 2
    assert report["arms"]["fulltext_direct"]["cost"]["model_calls"] == 2
    assert report["arms"]["local_followup"]["correct_concrete"]["count"] == 1
    assert report["retrieval"]["requested"] == 1
    assert (run / "review_report.html").exists()


@pytest.mark.asyncio
async def test_decisive_initial_is_carried_forward_but_direct_still_runs(material, monkeypatch):
    _, prep, runner, scorer = modules()
    install_local_transport(monkeypatch, prep, runner)
    plan = await freeze(material, prep)
    calls = fake_model(monkeypatch, runner, {"initial": "DECISIVE", "fulltext_direct": "CONTRADICTED"})
    run = material["root"] / "run"
    await runner.run_async(plan, run)
    result = scorer.score(run, material["gold"], material["root"] / "score.json")
    assert len(calls) == result["actual_cost"]["model_calls"] == 2
    assert result["arms"]["local_followup"]["cost"]["model_calls"] == 1
    assert result["arms"]["fulltext_direct"]["cost"]["model_calls"] == 2
    assert result["retrieval"]["requested"] == 0
    assert result["arms"]["fulltext_direct"]["false_concrete"]["count"] == 1
    assert result["paired_correct_concrete"]["right_wins"] == ["dev_001"]


@pytest.mark.asyncio
@pytest.mark.parametrize("initial", ["NO_GAP", "BAD_GAP"])
async def test_missing_or_invalid_gap_stays_in_denominator(material, monkeypatch, initial):
    _, prep, runner, scorer = modules()
    install_local_transport(monkeypatch, prep, runner)
    plan = await freeze(material, prep)
    calls = fake_model(monkeypatch, runner, {"initial": initial})
    run = material["root"] / "run"
    await runner.run_async(plan, run)
    result = scorer.score(run, material["gold"], material["root"] / "score.json")
    arm = result["arms"]["local_followup"]
    assert arm["metrics"]["total"] == 1
    assert arm["metrics"]["confusion"]["SUPPORT"]["NEI"] == 1
    assert arm["workflow_error_cases"] == 1
    assert arm["cost"]["model_calls"] == 1
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_rejected_second_label_remains_raw_and_unknown_usage_is_not_zero(material, monkeypatch):
    _, prep, runner, scorer = modules()
    install_local_transport(monkeypatch, prep, runner)
    plan = await freeze(material, prep)
    fake_model(monkeypatch, runner, {"initial": "NEI", "local_followup": "BAD_QUOTE"}, missing_usage=True)
    run = material["root"] / "run"
    await runner.run_async(plan, run)
    result = scorer.score(run, material["gold"], material["root"] / "score.json")
    arm = result["arms"]["local_followup"]
    assert arm["metrics"]["confusion"]["SUPPORT"]["SUPPORT"] == 1
    assert arm["metrics"]["rejected"] == 1
    assert arm["record_accepted_cases"] == 0
    assert arm["cost"]["reported_tokens"]["input_tokens"] is None
    assert result["actual_cost"]["partial_token_subtotals"]["input_tokens"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("second", [{"initial": "TOOLS"},
                                  {"initial": "NEI", "fulltext_direct": "FAIL", "local_followup": "FAIL"},
                                  {"initial": "NEI", "fulltext_direct": "DUPLICATE_THREAD"}])
async def test_isolation_or_all_failed_group_stops_and_cannot_score(material, monkeypatch, second):
    _, prep, runner, scorer = modules()
    install_local_transport(monkeypatch, prep, runner)
    plan = await freeze(material, prep)
    calls = fake_model(monkeypatch, runner, second)
    run = material["root"] / "run"
    with pytest.raises(RuntimeError):
        await runner.run_async(plan, run)
    assert len(calls) <= 3
    if second["initial"] == "TOOLS":
        assert len(calls) == 1
    manifest = json.loads((run / "manifest.json").read_text())
    assert manifest["status"] == "incomplete"
    with pytest.raises(ValueError, match="Incomplete"):
        scorer.score(run, material["gold"], material["root"] / "score.json")


@pytest.mark.asyncio
async def test_one_failed_second_attempt_is_a_completed_denominator_case(material, monkeypatch):
    _, prep, runner, scorer = modules()
    install_local_transport(monkeypatch, prep, runner)
    plan = await freeze(material, prep)
    fake_model(monkeypatch, runner, {"initial": "NEI", "fulltext_direct": "FAIL"})
    run = material["root"] / "run"
    await runner.run_async(plan, run)
    result = scorer.score(run, material["gold"], material["root"] / "score.json")
    assert result["arms"]["fulltext_direct"]["metrics"]["errors"] == 1
    assert result["arms"]["fulltext_direct"]["metrics"]["total"] == 1


@pytest.mark.asyncio
async def test_scorer_rejects_changed_or_duplicate_results_before_opening_gold(material, monkeypatch):
    helper, prep, runner, scorer = modules()
    install_local_transport(monkeypatch, prep, runner)
    plan = await freeze(material, prep)
    fake_model(monkeypatch, runner, {"initial": "NEI"})
    run = material["root"] / "run"
    await runner.run_async(plan, run)
    rows = json.loads((run / "rows.json").read_text())
    (run / "rows.json").write_text(json.dumps(rows + [rows[0]]))
    with pytest.raises(ValueError, match="changed|checksum"):
        scorer.score(run, material["gold"], material["root"] / "score.json")
    manifest = json.loads((run / "manifest.json").read_text())
    manifest["files"] = helper.file_hashes(run)
    (run / "manifest.json").write_text(json.dumps(manifest))
    original_open = Path.open

    def no_gold(path, *args, **kwargs):
        assert path.resolve() != material["gold"].resolve(), "invalid results opened gold"
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", no_gold)
    with pytest.raises(ValueError, match="exactly|duplicate|cover"):
        scorer.score(run, material["gold"], material["root"] / "score.json")


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["request", "prompt"])
async def test_scorer_rechecks_request_and_rendered_prompt_before_gold(material, monkeypatch, tamper):
    helper, prep, runner, scorer = modules()
    install_local_transport(monkeypatch, prep, runner)
    plan = await freeze(material, prep)
    fake_model(monkeypatch, runner, {"initial": "NEI"})
    run = material["root"] / "run"
    await runner.run_async(plan, run)
    requests = [json.loads(line) for line in (run / "requests.jsonl").read_text().splitlines()]
    if tamper == "request":
        requests[0]["stage"] = "unrecorded_stage"
    else:
        attempts = [json.loads(line) for line in (run / "attempts.jsonl").read_text().splitlines()]
        target = next(row for row in attempts if row["stage"] == "fulltext_direct")
        altered = b"An altered prompt must never be silently scored."
        (run / target["prompt_file"]).write_bytes(altered)
        (run / target["attempt"] / "prompt.txt").write_bytes(altered)
        target["prompt_sha256"] = hashlib.sha256(altered).hexdigest()
        next(row for row in requests if row["attempt"] == target["attempt"])["prompt_sha256"] = target["prompt_sha256"]
        (run / "attempts.jsonl").write_text("\n".join(json.dumps(row) for row in attempts) + "\n")
    (run / "requests.jsonl").write_text("\n".join(json.dumps(row) for row in requests) + "\n")
    manifest = json.loads((run / "manifest.json").read_bytes())
    manifest["files"] = helper.file_hashes(run)
    (run / "manifest.json").write_text(json.dumps(manifest))
    original_open = Path.open
    def no_gold(path, *args, **kwargs):
        assert path.resolve() != material["gold"].resolve(), "inconsistent run opened gold"
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", no_gold)
    with pytest.raises(ValueError, match="[Pp]rompt|[Rr]equest"):
        scorer.score(run, material["gold"], material["root"] / "score.json")
