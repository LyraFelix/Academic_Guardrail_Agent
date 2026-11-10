"""Freeze public inputs, source bytes, real MCP packets and prompts without gold."""

import argparse
import asyncio
import json
from pathlib import Path
import re

from academic_guardrail.core.review_models import ClientJudgment
from benchmarks.datasets import sha256, write_json
from benchmarks.local_followup_evaluation import (
    COMMON_INSTRUCTIONS, PROTOCOL, PROTOCOL_RULES, SECOND_INSTRUCTIONS,
    check_packet, file_hashes, first_prompt, load_plan, read_inputs,
    runtime_code_hashes, second_template,
)
from benchmarks.runner import _code_record
from scripts.client_review_batch import call, now, server
from scripts.codex_review_client import MODEL, REASONING, strict_schema
from scripts.validate_local_followup import complete_packet


async def prepare(inputs_path, refs_dir, output, expected_gold_sha256):
    if not re.fullmatch(r"[0-9a-f]{64}", expected_gold_sha256):
        raise ValueError("Provide the selected partition's expected gold SHA256, never a gold path")
    inputs_path, refs_dir, output = (Path(value).resolve() for value in (inputs_path, refs_dir, output))
    inputs = read_inputs(inputs_path)
    if not refs_dir.is_dir():
        raise ValueError("refs_dir must exist")
    sources = {}
    for item in inputs:
        source = Path(item["source_path"])
        if not source.is_absolute() or not source.resolve().is_relative_to(refs_dir):
            raise ValueError("Every absolute source_path must stay inside refs_dir")
        sources[str(source.resolve())] = sha256(source)
    code = runtime_code_hashes()
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"status": "incomplete", "started_utc": now(), "cases": len(inputs), "prepared": 0}
    try:
        (output / "inputs.jsonl").write_bytes(inputs_path.read_bytes())
        write_json(output / "schema.json", strict_schema(ClientJudgment.model_json_schema()))
        (output / "common_instructions.txt").write_bytes(COMMON_INSTRUCTIONS.encode("utf-8"))
        (output / "second_instructions.txt").write_bytes(SECOND_INSTRUCTIONS.encode("utf-8"))
        (output / "packets").mkdir()
        (output / "prompts").mkdir()
        cases = []
        with (output / "transcript.jsonl").open("x", encoding="utf-8") as log:
            async with server(output, output) as session:
                for index, item in enumerate(inputs):
                    case = {"id": item["id"], "input": item}
                    views = {}
                    for scope in ("abstract", "full_text"):
                        packet = await call(session, "prepare_local_claim_review", {
                            "claim": item["claim"], "citation_str_or_doi": item["citation_str_or_doi"],
                            "refs_dir": str(refs_dir), "initial_scope": scope}, log)
                        packet = await complete_packet(session, packet, log)
                        check_packet(output, packet, item, scope)
                        filename = f"packets/{index:03d}_{scope}.json"
                        write_json(output / filename, packet)
                        case[f"{scope}_packet"] = filename
                        views[scope] = packet
                    case["initial_prompt"] = f"prompts/{index:03d}_initial.txt"
                    case["direct_template"] = f"prompts/{index:03d}_direct_template.txt"
                    (output / case["initial_prompt"]).write_bytes(first_prompt(views["abstract"]).encode("utf-8"))
                    (output / case["direct_template"]).write_bytes(second_template(views["full_text"]).encode("utf-8"))
                    cases.append(case)
                    manifest["prepared"] += 1
        if sources != {name: sha256(Path(name)) for name in sources} or code != runtime_code_hashes():
            raise ValueError("Sources or runtime code changed during preparation")
        if inputs != read_inputs(output / "inputs.jsonl"):
            raise ValueError("Inputs changed while freezing")
        plan = {"protocol": PROTOCOL, "rules": PROTOCOL_RULES, "created_utc": now(),
                "partition": inputs[0]["partition"], "cases": cases,
                "refs_dir": str(refs_dir), "source_sha256": sources,
                "runtime_code_sha256": code, "code": _code_record(),
                "model": MODEL, "reasoning": REASONING,
                "expected_gold_sha256": expected_gold_sha256,
                "max_actual_cli_calls": 3 * len(cases), "max_effective_calls_per_arm_case": 2,
                "dynamic_prompt_renderer": "benchmarks.local_followup_evaluation.second_prompt"}
        write_json(output / "plan.json", plan)
        manifest["status"] = "completed"
    finally:
        manifest.update(finished_utc=now(), files=file_hashes(output))
        write_json(output / "manifest.json", manifest)
    load_plan(output / "plan.json")
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--refs-dir", type=Path, required=True)
    parser.add_argument("--expected-gold-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(prepare(args.inputs, args.refs_dir, args.output, args.expected_gold_sha256))
    print(json.dumps({"protocol": result["protocol"], "cases": len(result["cases"]), "gold_opened": False}))


if __name__ == "__main__":
    main()
