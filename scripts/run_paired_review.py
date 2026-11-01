"""Run a frozen plan in fresh Codex contexts, then validate all arms equally.

Raw model answers are immutable. Only MCP-arm answers are also recorded over the
actual MCP transport. No gold file is opened and no rejected answer is repaired.
"""

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import time

from academic_guardrail.core.claim_review import validate_client_judgment
from academic_guardrail.core.review_models import ClientJudgment
from academic_guardrail.core.review_store import ReviewStore, content_digest
from benchmarks.client_comparison import ARMS, make_prompt, raw_prediction
from benchmarks.datasets import sha256, write_json
from benchmarks.runner import _code_record
from scripts.client_review_batch import call, load_batch, now, server
from scripts.codex_review_client import MODEL, REASONING, invoke


def load_plan(plan_path, batch):
    content = plan_path.read_bytes()
    plan = json.loads(content)
    if plan["model"] != MODEL or plan["reasoning"] != REASONING:
        raise ValueError("Frozen model configuration differs from this adapter")
    _, packets = load_batch(batch)
    if sha256(batch / "manifest.json") != plan["batch_manifest_sha256"]:
        raise ValueError("Plan belongs to a different evidence batch")
    schema_bytes = (plan_path.parent / "schema.json").read_bytes()
    if hashlib.sha256(schema_bytes).hexdigest() != plan["schema_sha256"]:
        raise ValueError("Schema changed after freezing")
    expected = {(packet["id"], arm) for packet in packets for arm in ARMS}
    schedule = plan["schedule"]
    if len(schedule) != len(expected) or {(row["id"], row["arm"]) for row in schedule} != expected:
        raise ValueError("Plan must contain exactly one decision per arm and case")
    prompts = []
    indexed = {packet["id"]: packet for packet in packets}
    for packet in packets:
        load_frozen_packet(batch, packet)
    for item in schedule:
        filename = item["prompt_file"]
        if Path(filename).name != filename:
            raise ValueError("Prompt filename must stay within the plan directory")
        prompt = (plan_path.parent / filename).read_bytes()
        if hashlib.sha256(prompt).hexdigest() != item["prompt_sha256"]:
            raise ValueError("Prompt changed after freezing")
        if prompt.decode("utf-8") != make_prompt(indexed[item["id"]], item["arm"]):
            raise ValueError("Prompt no longer matches the source packet and frozen workflow")
        prompts.append(prompt.decode("utf-8"))
    return plan, content, packets, prompts, json.loads(schema_bytes)


def load_frozen_packet(batch, view):
    packet = ReviewStore(batch / "stored").load_packet(view["packet_id"])
    if content_digest(packet.model_dump(mode="json")) != view["packet_sha256"]:
        raise ValueError("Stored packet differs from the frozen client evidence")
    return packet


def inspect_answer(packet, receipt):
    """Apply the identical offline checker to all arms, separate from raw scoring."""
    response = receipt.get("response")
    indexed = {item.id: item.text for item in packet.evidence}
    quotes = response.get("quotes", []) if isinstance(response, dict) else []
    quotes = quotes if isinstance(quotes, list) else []
    exact = sum(isinstance(item, dict) and isinstance(item.get("quote"), str) and bool(item["quote"])
                and isinstance(item.get("evidence_id"), str)
                and item["evidence_id"] in indexed and item["quote"] in indexed[item["evidence_id"]]
                for item in quotes)
    error = receipt.get("error")
    if error is None:
        try:
            validate_client_judgment(packet, ClientJudgment.model_validate(response))
        except ValueError as exc:
            error = str(exc)
    return {"prediction": raw_prediction(receipt), "validation_error": error,
            "quotes_valid": bool(quotes) and exact == len(quotes),
            "quote_count": len(quotes), "exact_quote_count": exact,
            "usage": receipt.get("usage"), "elapsed_seconds": receipt["elapsed_seconds"]}


async def record_mcp(batch, output, packets, rows, receipts):
    output.mkdir()
    started = time.monotonic()
    records = []
    with (output / "transcript.jsonl").open("x", encoding="utf-8") as log:
        async with server(batch, output) as session:
            for row, receipt in zip(rows, receipts):
                if row["arm"] != "mcp":
                    continue
                packet = packets[row["id"]]
                error, record = None, None
                try:
                    judgment = ClientJudgment.model_validate(receipt.get("response"))
                    record = await call(session, "record_claim_review", {
                        "packet_id": packet["packet_id"], "expected_packet_sha256": packet["packet_sha256"],
                        "judgment": judgment.model_dump(mode="json")}, log)
                except ValueError as exc:
                    error = str(exc)
                records.append({"id": row["id"], "record": record, "error": error})
                # A transport discrepancy is visible; never rewrite the raw model conclusion.
                row["mcp_record_error"] = error
    write_json(output / "records.json", records)
    return time.monotonic() - started


def run(plan_path, batch, output, timeout=120):
    if not 1 <= timeout <= 600:
        raise ValueError("Timeout must be between 1 and 600 seconds")
    plan, plan_bytes, packets, prompts, schema = load_plan(plan_path, batch)
    output.mkdir(parents=True, exist_ok=False)
    (output / "plan.json").write_bytes(plan_bytes)
    manifest = {"status": "incomplete", "started_utc": now(), "code": _code_record(),
                "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(), "model": plan["model"],
                "reasoning": plan["reasoning"], "planned_decisions": len(prompts),
                "attempted": 0, "timeout_seconds": timeout, "max_parallel": 3}
    manifest["cli_version"] = subprocess.run(["codex", "--version"], capture_output=True, text=True, check=True).stdout.strip()
    receipts, rows = [], []
    indexed = {packet["id"]: packet for packet in packets}
    try:
        with (output / "attempts.jsonl").open("x", encoding="utf-8") as attempts:
            with ThreadPoolExecutor(max_workers=3) as executor:
                for start in range(0, len(prompts), 3):
                    futures = [executor.submit(invoke, prompts[i], schema, output / f"attempt_{i:03d}", timeout)
                               for i in range(start, min(start + 3, len(prompts)))]
                    for offset, future in enumerate(futures):
                        i, receipt = start + offset, future.result()
                        item = plan["schedule"][i]
                        packet = load_frozen_packet(batch, indexed[item["id"]])
                        row = {"id": item["id"], "arm": item["arm"], "attempt": f"attempt_{i:03d}",
                               **inspect_answer(packet, receipt)}
                        receipts.append(receipt)
                        rows.append(row)
                        attempts.write(json.dumps(row, ensure_ascii=False) + "\n")
                        attempts.flush()
                        manifest["attempted"] += 1
                    print(json.dumps({"completed": len(rows), "planned": len(prompts),
                                      "execution_errors": sum(row["prediction"] == "ERROR" for row in rows)}), flush=True)
                    if any(receipt.get("tool_items") or receipt.get("event_stream_valid") is False
                           or receipt.get("error") in {"unexpected_tool_use", "invalid_event_stream"}
                           for receipt in receipts[-len(futures):]):
                        raise RuntimeError("Isolation could not be verified; stop before further model calls")
                    if all(receipt.get("error") for receipt in receipts[-len(futures):]):
                        raise RuntimeError("All concurrent attempts failed; preserve artifacts and stop before more calls")
        manifest["mcp_record_seconds"] = asyncio.run(record_mcp(batch, output / "mcp_records", indexed, rows, receipts))
        write_json(output / "rows.json", rows)
        load_plan(plan_path, batch)
        if plan_path.read_bytes() != plan_bytes:
            raise ValueError("Plan changed during run")
        manifest["status"] = "completed"
    finally:
        manifest["finished_utc"] = now()
        manifest["files"] = {str(path.relative_to(output)).replace("\\", "/"): sha256(path)
                             for path in sorted(output.rglob("*")) if path.is_file() and path.name != "manifest.json"}
        write_json(output / "manifest.json", manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    result = run(args.plan, args.batch, args.output, args.timeout)
    print(json.dumps({"status": result["status"], "attempted": result["attempted"]}))
