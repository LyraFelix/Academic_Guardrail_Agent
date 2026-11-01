"""Replayable MCP client batch: prepare inputs, submit client decisions, then score.

This script never generates model decisions. The existing client model fills a
JSONL file after reading packets; score is the only command that opens gold.
Run with: python -m scripts.client_review_batch --help
"""

import argparse
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Literal

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, ConfigDict, Field

from academic_guardrail.core.review_models import ClientJudgment
from benchmarks.datasets import read_records, sha256, unique_by_id, write_json
from benchmarks.metrics import rate
from benchmarks.runner import _code_record
from benchmarks.schema import GoldCase, InputCase
from scripts.validate_phase_two import CHILD, GUARDS


class ClientSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    judgment: ClientJudgment


class ClientProfile(BaseModel):
    """Record who made the decisions; never infer a model name from the host."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    application: str = Field(min_length=1, max_length=200)
    model_id: str | None = Field(default=None, min_length=1, max_length=200)
    execution_mode: Literal["interactive", "api", "unspecified"] = "unspecified"
    context_description: str = Field(min_length=1, max_length=3000)


def now():
    return datetime.now(timezone.utc).isoformat()


@asynccontextmanager
async def server(batch, output):
    env = {**os.environ, "ACADEMIC_GUARDRAIL_REVIEW_DIR": str(batch / "stored"),
           "RETRACTION_DB_PATH": ":memory:", "PYTHONDONTWRITEBYTECODE": "1"}
    boundary = output / "boundary_attempts.json"
    params = StdioServerParameters(command=sys.executable,
                                   args=["-X", "utf8", "-c", CHILD, str(boundary), json.dumps(GUARDS)], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session
    if json.loads(boundary.read_text(encoding="utf-8")):
        raise ValueError("Offline boundary was crossed")


async def call(session, name, arguments, transcript):
    result = await session.call_tool(name, arguments)
    transcript.write(json.dumps({"tool": name, "arguments": arguments,
                                 "response": result.model_dump(mode="json")}, ensure_ascii=False) + "\n")
    transcript.flush()
    if result.isError:
        raise ValueError("; ".join(block.text for block in result.content if hasattr(block, "text")))
    return result.structuredContent or json.loads(next(block.text for block in result.content if hasattr(block, "text")))


async def prepare(inputs_path, destination, dataset_manifest=None):
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "inputs.jsonl").write_bytes(inputs_path.read_bytes())
    inputs = read_records(destination / "inputs.jsonl", InputCase)
    if not inputs:
        raise ValueError("Empty input batch")
    manifest = {"status": "incomplete", "started_utc": now(), "count": len(inputs), "processed": 0,
                "inputs_sha256": sha256(destination / "inputs.jsonl"), "code": _code_record(),
                "batch_script_sha256": sha256(Path(__file__))}
    if dataset_manifest is not None:
        metadata = dataset_manifest.read_bytes()  # Hashes/protocol only, no gold labels.
        dataset = json.loads(metadata)
        if dataset["files"]["inputs.jsonl"] != manifest["inputs_sha256"]:
            raise ValueError("Dataset manifest does not match the input snapshot")
        manifest.update(expected_gold_sha256=dataset["files"]["gold.jsonl"],
                        dataset_manifest_sha256=hashlib.sha256(metadata).hexdigest())
        (destination / "dataset_manifest.json").write_bytes(metadata)
    try:
        with (destination / "transcript.jsonl").open("x", encoding="utf-8") as log, \
                (destination / "packets.jsonl").open("x", encoding="utf-8") as packets:
            async with server(destination, destination) as session:
                for item in inputs:
                    packet = await call(session, "prepare_claim_review", {"claim": item.claim,
                                        "reference_text": "\n\n".join(item.sentences), "offline": True}, log)
                    following = packet["next_offset"]
                    while following is not None:
                        page = await call(session, "read_claim_evidence", {"packet_id": packet["packet_id"], "offset": following}, log)
                        if page["packet_sha256"] != packet["packet_sha256"]:
                            raise ValueError("Evidence snapshot changed between pages")
                        packet["evidence"].extend(page["evidence"])
                        following = page["next_offset"]
                    packet["next_offset"] = None
                    packets.write(json.dumps({"id": item.id, **packet}, ensure_ascii=False) + "\n")
                    packets.flush()
                    manifest["processed"] += 1
        if sha256(destination / "inputs.jsonl") != manifest["inputs_sha256"]:
            raise ValueError("Input snapshot changed during preparation")
        manifest.update(status="completed", packets_sha256=sha256(destination / "packets.jsonl"))
    finally:
        manifest["finished_utc"] = now()
        write_json(destination / "manifest.json", manifest)
    return {"batch": str(destination), "cases": len(inputs), "next": "Client reads packets.jsonl and writes judgments JSONL; no gold has been opened"}


def load_batch(batch):
    manifest = json.loads((batch / "manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "completed":
        raise ValueError("Incomplete prepared batch")
    contents = {}
    for name in ("inputs", "packets"):
        contents[name] = (batch / f"{name}.jsonl").read_bytes()
        if hashlib.sha256(contents[name]).hexdigest() != manifest[f"{name}_sha256"]:
            raise ValueError(f"Batch checksum mismatch: {name}")
    inputs = unique_by_id([InputCase.model_validate_json(line) for line in contents["inputs"].decode("utf-8").splitlines()])
    packets = [json.loads(line) for line in contents["packets"].decode("utf-8").splitlines()]
    if len(packets) != len(inputs) or {packet["id"] for packet in packets} != set(inputs):
        raise ValueError("Packet/input IDs differ")
    return manifest, packets


async def submit(batch, judgments_path, destination, client_profile_path=None):
    _, packets = load_batch(batch)
    batch_hash = sha256(batch / "manifest.json")
    content = judgments_path.read_bytes()
    profile = (ClientProfile.model_validate_json(client_profile_path.read_bytes()) if client_profile_path else
               ClientProfile(application="unspecified", context_description="Client identity was not recorded."))
    judgments = unique_by_id([ClientSubmission.model_validate_json(line) for line in content.decode("utf-8").splitlines() if line.strip()])
    if set(judgments) != {packet["id"] for packet in packets}:
        raise ValueError("Require exactly one client submission per input case")
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "judgments.jsonl").write_bytes(content)
    manifest = {"status": "incomplete", "started_utc": now(), "count": len(packets), "processed": 0, "errors": 0,
                "batch_manifest_sha256": batch_hash,
                "judgments_sha256": sha256(destination / "judgments.jsonl"), "code": _code_record(),
                "batch_script_sha256": sha256(Path(__file__))}
    manifest["client"] = profile.model_dump(mode="json")
    try:
        with (destination / "transcript.jsonl").open("x", encoding="utf-8") as log, \
                (destination / "predictions.jsonl").open("x", encoding="utf-8") as predictions:
            async with server(batch, destination) as session:
                for packet in packets:
                    try:
                        record = await call(session, "record_claim_review", {"packet_id": packet["packet_id"],
                                            "expected_packet_sha256": packet["packet_sha256"],
                                            "judgment": judgments[packet["id"]].judgment.model_dump(mode="json")}, log)
                        if record["packet_sha256"] != packet["packet_sha256"]:
                            raise ValueError("Recorded evidence differs from the client-reviewed snapshot")
                        row = {"id": packet["id"], "record": record, "error": None}
                    except ValueError as error:
                        row = {"id": packet["id"], "record": None, "error": str(error)}
                        manifest["errors"] += 1
                    predictions.write(json.dumps(row, ensure_ascii=False) + "\n")
                    predictions.flush()
                    manifest["processed"] += 1
        load_batch(batch)
        if sha256(batch / "manifest.json") != batch_hash or sha256(destination / "judgments.jsonl") != manifest["judgments_sha256"]:
            raise ValueError("Batch or judgment snapshot changed during submission")
        manifest.update(status="completed_with_errors" if manifest["errors"] else "completed",
                        predictions_sha256=sha256(destination / "predictions.jsonl"))
    finally:
        manifest["finished_utc"] = now()
        write_json(destination / "manifest.json", manifest)
    return manifest


def score(batch, submission, gold_path, destination):
    batch_manifest, packets = load_batch(batch)
    manifest = json.loads((submission / "manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] not in {"completed", "completed_with_errors"}:
        raise ValueError("Incomplete submitted batch")
    if manifest["batch_manifest_sha256"] != sha256(batch / "manifest.json"):
        raise ValueError("Submission belongs to a different batch")
    contents = {}
    for name in ("predictions", "judgments"):
        contents[name] = (submission / f"{name}.jsonl").read_bytes()
        if hashlib.sha256(contents[name]).hexdigest() != manifest[f"{name}_sha256"]:
            raise ValueError(f"Submission checksum mismatch: {name}")
    rows = [json.loads(line) for line in contents["predictions"].decode("utf-8").splitlines()]
    gold_content = gold_path.read_bytes()  # First gold read in this workflow.
    gold_hash = hashlib.sha256(gold_content).hexdigest()
    if not batch_manifest.get("expected_gold_sha256"):
        raise ValueError("Scoring requires a dataset manifest pinned during preparation")
    if gold_hash != batch_manifest["expected_gold_sha256"]:
        raise ValueError("Gold checksum differs from the snapshot pinned before submission")
    gold = unique_by_id([GoldCase.model_validate_json(line) for line in gold_content.decode("utf-8").splitlines()])
    if any(item.label not in {"SUPPORT", "CONTRADICT", "NEI"} or item.expected_state is not None for item in gold.values()):
        raise ValueError("Client pilot requires three-way fact labels")
    ids = {packet["id"] for packet in packets}
    if len(rows) != len(ids) or {row["id"] for row in rows} != ids or set(gold) != ids:
        raise ValueError("Inputs, predictions and gold must cover the same unique IDs")
    mapping = {"SUPPORTED": "SUPPORT", "CONTRADICTED": "CONTRADICT", "NOT_ENOUGH_EVIDENCE": "NEI", "UNCERTAIN": "ABSTAIN"}
    table = {label: {state: 0 for state in ("SUPPORT", "CONTRADICT", "NEI", "ABSTAIN", "ERROR")}
             for label in ("SUPPORT", "CONTRADICT", "NEI")}
    cases = []
    for row in rows:
        prediction = "ERROR" if row["error"] else mapping[row["record"]["judgment"]["conclusion"]]
        table[gold[row["id"]].label][prediction] += 1
        cases.append({"id": row["id"], "gold": gold[row["id"]].label, "prediction": prediction,
                      "correct": prediction == gold[row["id"]].label, "error": row["error"]})
    correct = sum(table[label][label] for label in table)
    unresolved = sum(values["ABSTAIN"] + values["ERROR"] for values in table.values())
    concrete = sum(values["SUPPORT"] + values["CONTRADICT"] for values in table.values())
    concrete_correct = table["SUPPORT"]["SUPPORT"] + table["CONTRADICT"]["CONTRADICT"]
    nei = sum(values["NEI"] for values in table.values())
    class_metrics = {label: {"precision": rate(table[label][label], sum(values[label] for values in table.values())),
                             "recall": rate(table[label][label], sum(table[label].values()))}
                     for label in table}
    result = {"protocol": "interactive_client_given_source_v1", "total": len(rows), "state_by_gold": table,
              "client": manifest.get("client", {"application": "unrecorded", "model_id": None}),
              "class_metrics": class_metrics, "cases": cases,
              "label_agreement": rate(correct, len(rows)),
              "label_coverage": rate(len(rows) - unresolved, len(rows)),
              "support_or_contradict_coverage": rate(concrete, len(rows)),
              "agreement_on_support_or_contradict": rate(concrete_correct, concrete),
              "not_enough_evidence_rate": rate(nei, len(rows)),
              "abstention_or_error_rate": rate(unresolved, len(rows)),
              "errors": sum(row["error"] is not None for row in rows), "gold_sha256": gold_hash,
              "batch_manifest_sha256": sha256(batch / "manifest.json"),
              "submission_manifest_sha256": sha256(submission / "manifest.json"),
              "batch_script_sha256": sha256(Path(__file__)),
              "boundary": "NEI is not support/refutation; client-generated labels; quote validation does not certify semantic correctness; no bare-model comparison"}
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preparation = commands.add_parser("prepare")
    preparation.add_argument("--inputs", type=Path, required=True)
    preparation.add_argument("--output", type=Path, required=True)
    preparation.add_argument("--dataset-manifest", type=Path,
                             help="Pin the gold checksum without reading labels; required for later scoring")
    submission = commands.add_parser("submit")
    submission.add_argument("--batch", type=Path, required=True)
    submission.add_argument("--judgments", type=Path, required=True)
    submission.add_argument("--output", type=Path, required=True)
    submission.add_argument("--client-profile", type=Path, help="JSON with host, model ID (or null), mode and context")
    scoring = commands.add_parser("score")
    scoring.add_argument("--batch", type=Path, required=True)
    scoring.add_argument("--submission", type=Path, required=True)
    scoring.add_argument("--gold", type=Path, required=True)
    scoring.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = asyncio.run(prepare(args.inputs, args.output, args.dataset_manifest))
    elif args.command == "submit":
        result = asyncio.run(submit(args.batch, args.judgments, args.output, args.client_profile))
    else:
        result = score(args.batch, args.submission, args.gold, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
