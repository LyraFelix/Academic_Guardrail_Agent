"""Execute a frozen local-source comparison; never open gold or repair raw answers."""

import argparse
import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import time

from academic_guardrail.core.review_store import ReviewStore
from benchmarks.datasets import sha256, write_json
from benchmarks.local_followup_evaluation import (
    check_packet, file_hashes, inspect_receipt, load_packet_view, load_plan, second_prompt,
)
from scripts.client_review_batch import call, now, server
from scripts.codex_review_client import invoke
from scripts.validate_local_followup import complete_packet


def cli_version():
    return subprocess.run(["codex", "--version"], capture_output=True, text=True,
                          check=True, timeout=15).stdout.strip()


def check_isolation(receipts, seen_threads):
    for receipt in receipts:
        if receipt.get("tool_items") or receipt.get("event_stream_valid") is not True or receipt.get("error") in {
                "unexpected_tool_use", "invalid_event_stream"}:
            raise RuntimeError("Isolation could not be verified; stop before further model calls")
        threads = receipt.get("thread_ids", [])
        if len(threads) != len(set(threads)) or any(thread in seen_threads for thread in threads):
            raise RuntimeError("CLI thread reused; stop before further model calls")
        if receipt.get("error") is None and len(threads) != 1:
            raise RuntimeError("Successful invocation lacks one isolated CLI thread")
        seen_threads.update(threads)
    if all(receipt.get("error") for receipt in receipts):
        raise RuntimeError("All concurrent attempts failed; stop before further model calls")


async def record_valid(session, runtime, view, receipt, inspection, log):
    if inspection["validation_error"] is not None:
        return None, "offline_validation_rejected: " + inspection["validation_error"]
    try:
        # Send the original object, not a reserialized/repaired ClientJudgment.
        record = await call(session, "record_claim_review", {
            "packet_id": view["packet_id"], "expected_packet_sha256": view["packet_sha256"],
            "judgment": receipt["response"]}, log)
        saved = ReviewStore(runtime / "stored").load_review(record["review_id"])
        if record["packet_sha256"] != view["packet_sha256"] or record["review_sha256"] != saved["review_sha256"]:
            raise ValueError("Recorded packet or review digest differs from the actual stored record")
        return record, None
    except (ValueError, OSError) as exc:
        return None, str(exc)


async def run_async(plan_path, output, timeout=180):
    if not 1 <= timeout <= 600:
        raise ValueError("Timeout must be between 1 and 600 seconds")
    plan_path, output = Path(plan_path).resolve(), Path(output).resolve()
    plan, _, schema = load_plan(plan_path)
    if output.is_relative_to(plan_path.parent):
        raise ValueError("Run output must be outside the immutable prepared directory")
    plan_hash = sha256(plan_path)
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    manifest = {"status": "incomplete", "started_utc": now(), "protocol": plan["protocol"],
                "model": plan["model"], "reasoning": plan["reasoning"], "plan_sha256": plan_hash,
                "planned_cases": len(plan["cases"]), "completed_cases": 0, "actual_cli_calls": 0,
                "max_actual_cli_calls": plan["max_actual_cli_calls"], "max_parallel": 2,
                "timeout_seconds": timeout, "gold_opened": False}
    attempts, rows, case_results, seen_threads = [], [], [], set()
    try:
        frozen, runtime, mcp_output = output / "frozen", output / "runtime", output / "mcp"
        shutil.copytree(plan_path.parent, frozen)
        shutil.copytree(frozen / "stored", runtime / "stored")
        (output / "plan.json").write_bytes(plan_path.read_bytes())
        (output / "prompts").mkdir()
        mcp_output.mkdir()
        manifest["cli_version"] = cli_version()
        with (output / "attempts.jsonl").open("x", encoding="utf-8") as attempt_log, \
                (output / "requests.jsonl").open("x", encoding="utf-8") as request_log, \
                (mcp_output / "transcript.jsonl").open("x", encoding="utf-8") as log:
            async with server(runtime, mcp_output) as session:

                def verify_freeze():
                    load_plan(plan_path)
                    load_plan(frozen / "plan.json")
                    if sha256(plan_path) != plan_hash:
                        raise ValueError("Plan changed during execution")

                async def judge(case, stage, view, prompt):
                    if manifest["actual_cli_calls"] >= plan["max_actual_cli_calls"]:
                        raise RuntimeError("Frozen actual invocation budget exceeded")
                    index = manifest["actual_cli_calls"]
                    manifest["actual_cli_calls"] += 1
                    name = f"attempt_{index:03d}_{stage}"
                    prompt_path = output / "prompts" / f"{name}.txt"
                    prompt_path.write_bytes(prompt.encode("utf-8"))
                    packet = check_packet(runtime, view, case["input"])
                    request = {"id": case["id"], "stage": stage, "attempt": name,
                               "packet_id": view["packet_id"], "packet_sha256": view["packet_sha256"],
                               "prompt_file": prompt_path.relative_to(output).as_posix(),
                               "prompt_sha256": sha256(prompt_path), "requested_utc": now()}
                    request_log.write(json.dumps(request, ensure_ascii=False) + "\n")
                    request_log.flush()
                    before = time.monotonic()
                    try:
                        receipt = await asyncio.to_thread(invoke, prompt, schema, output / name, timeout)
                    except Exception as exc:
                        receipt = {"response": None, "error": f"invoke_exception: {type(exc).__name__}: {exc}",
                                   "usage": None, "elapsed_seconds": time.monotonic() - before,
                                   "event_stream_valid": False, "thread_ids": [], "tool_items": []}
                        (output / name).mkdir(exist_ok=True)
                        write_json(output / name / "harness_error.json", receipt)
                    # Preserve the receipt even if a future adapter raises before writing its own.
                    write_json(output / name / "observed_receipt.json", receipt)
                    inspection = inspect_receipt(packet, receipt)
                    row = {**request, **inspection, "error": receipt.get("error")}
                    attempts.append(row)
                    attempt_log.write(json.dumps(row, ensure_ascii=False) + "\n")
                    attempt_log.flush()
                    print(json.dumps({"id": case["id"], "stage": stage, "finished_attempts": len(attempts),
                                      "actual_cli_calls": manifest["actual_cli_calls"],
                                      "max_actual_cli_calls": plan["max_actual_cli_calls"],
                                      "prediction": row["prediction"], "error": row["error"]}), flush=True)
                    return receipt, row

                report_ids = []
                for case in plan["cases"]:
                    verify_freeze()
                    abstract = load_packet_view(frozen, case["abstract_packet"])
                    full = load_packet_view(frozen, case["full_text_packet"])
                    first, initial = await judge(case, "initial", abstract,
                        (frozen / case["initial_prompt"]).read_text(encoding="utf-8"))
                    check_isolation([first], seen_threads)
                    before = time.monotonic()
                    first_record, first_error = await record_valid(session, runtime, abstract, first, initial, log)
                    timings = {"initial_record_seconds": time.monotonic() - before}
                    abstract_row = {**initial, "arm": "abstract_only", "cost_attempts": [initial["attempt"]],
                                    "mcp_record_error": first_error, "record_accepted": first_record is not None,
                                    "workflow_errors": [first_error] if first_error else []}
                    local = {**abstract_row, "arm": "local_followup"}
                    outcome = {"id": case["id"], "initial_attempt": initial["attempt"],
                               "initial_record": first_record, "initial_record_error": first_error,
                               "unresolved_initial": initial["prediction"] in {"NEI", "ABSTAIN"},
                               "lookup_requested": False, "retrieval_status": "NOT_REQUESTED",
                               "query_terms": [], "added_evidence_ids": [], "timings": timings}
                    response = first.get("response") or {}
                    gaps = response.get("missing_evidence", [])
                    outcome["declared_gap_count"] = len(gaps) if isinstance(gaps, list) else 0
                    followup = None
                    if outcome["unresolved_initial"]:
                        if first_record is None:
                            local["workflow_errors"] = [first_error or "initial_record_unavailable"]
                        elif not gaps:
                            local["workflow_errors"] = ["unresolved_initial_without_missing_evidence"]
                        else:
                            outcome["lookup_requested"] = True
                            before = time.monotonic()
                            try:
                                followup = await call(session, "follow_up_local_claim", {
                                    "review_id": first_record["review_id"],
                                    "expected_review_sha256": first_record["review_sha256"], "gap_index": 0}, log)
                                followup = await complete_packet(session, followup, log)
                                check_packet(runtime, followup, case["input"])
                                followup_file = f"followup_{manifest['completed_cases']:03d}.json"
                                write_json(output / followup_file, followup)
                                context = followup["local_review"]
                                outcome.update({key: context[key] for key in (
                                    "retrieval_status", "query_terms", "added_evidence_ids", "matched_passages",
                                    "total_passages", "search_scope")})
                                outcome["followup_packet"] = followup_file
                            except Exception as exc:
                                followup = None
                                outcome.update(retrieval_status="FAILED", lookup_error=str(exc))
                                local["workflow_errors"] = [f"lookup_failed: {exc}"]
                            timings["lookup_seconds"] = time.monotonic() - before
                    verify_freeze()
                    jobs = [judge(case, "fulltext_direct", full, second_prompt(full, first.get("response")))]
                    if followup is not None:
                        jobs.append(judge(case, "local_followup", followup, second_prompt(followup, first.get("response"))))
                    results = await asyncio.gather(*jobs)
                    check_isolation([receipt for receipt, _ in results], seen_threads)
                    direct_receipt, direct = results[0]
                    direct = {**direct, "arm": "fulltext_direct", "record_accepted": False,
                              "cost_attempts": [initial["attempt"], direct["attempt"]], "workflow_errors": []}
                    latest_record = first_record
                    if followup is not None:
                        final_receipt, final = results[1]
                        before = time.monotonic()
                        final_record, final_error = await record_valid(session, runtime, followup,
                                                                      final_receipt, final, log)
                        timings["final_record_seconds"] = time.monotonic() - before
                        local = {**final, "arm": "local_followup", "mcp_record_error": final_error,
                                 "record_accepted": final_record is not None,
                                 "cost_attempts": [initial["attempt"], final["attempt"]],
                                 "workflow_errors": [final_error] if final_error else []}
                        outcome.update(final_record=final_record, final_record_error=final_error)
                        latest_record = final_record or first_record
                    if latest_record is not None:
                        report_ids.append(latest_record["review_id"])
                    outcome.update(local_final_attempt=local["attempt"],
                                   direct_final_attempt=direct["attempt"], workflow_errors=local["workflow_errors"])
                    rows.extend([abstract_row, direct, local])
                    case_results.append(outcome)
                    manifest["completed_cases"] += 1
                    write_json(output / "rows.json", rows)
                    write_json(output / "cases.json", case_results)
                if report_ids:
                    before = time.monotonic()
                    manifest["report"] = await call(session, "generate_claim_review_report", {
                        "review_ids": report_ids, "output_path": str(output / "review_report.html")}, log)
                    manifest["report_seconds"] = time.monotonic() - before
                else:
                    manifest["report"] = {"status": "no_valid_recorded_judgments"}
        verify_freeze()
        manifest["status"] = "completed"
    except BaseException as exc:
        manifest["failure"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        # Partial rows and attempts are retained but are never eligible for full scoring.
        write_json(output / "rows.json", rows)
        write_json(output / "cases.json", case_results)
        manifest.update(finished_utc=now(), elapsed_seconds=time.monotonic() - started,
                        files=file_hashes(output))
        write_json(output / "manifest.json", manifest)
    return manifest


def run(plan_path, output, timeout=180):
    return asyncio.run(run_async(plan_path, output, timeout))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    result = run(args.plan, args.output, args.timeout)
    print(json.dumps({"status": result["status"], "actual_cli_calls": result["actual_cli_calls"]}))


if __name__ == "__main__":
    main()
