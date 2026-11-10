"""Exercise real offline MCP transport with scripted judgments; no model accuracy claim.

Run: python -m scripts.validate_local_followup --output <new-directory>
"""

import argparse
import asyncio
import json
from pathlib import Path
import shutil

from scripts.client_review_batch import call, server


async def complete_packet(session, packet, log):
    """Read every page of this exact stored snapshot before constructing a judgment."""
    following = packet["next_offset"]
    while following is not None:
        page = await call(session, "read_claim_evidence", {"packet_id": packet["packet_id"], "offset": following}, log)
        if page["packet_sha256"] != packet["packet_sha256"]:
            raise ValueError("Packet changed while paging")
        packet["evidence"].extend(page["evidence"])
        following = page["next_offset"]
    packet["next_offset"] = None
    return packet


def fixture_judgment(packet, *, final=False):
    value = {"conclusion": "SUPPORTED" if final else "NOT_ENOUGH_EVIDENCE",
             "rationale": "The result paragraph supplies the number." if final else "The abstract has no numerical result.",
             "reviewed_evidence_ids": [unit["id"] for unit in packet["evidence"]], "quotes": [],
             "checks": {"subject": "Same synthetic intervention.", "relation": "Mortality reduction.",
                        "numbers": "25% at six months.", "scope": "Adults only, same comparator.",
                        "counterevidence": "Read the adjacent limitation; the pediatric group is absent."},
             "client_model": "scripted fixture, not a model",
             "missing_evidence": [] if final else [{"kind": "RESULT", "claim_part": "mortality by 25%",
                  "question": "What mortality reduction was observed at six months?", "search_terms": ["mortality", "six months"]}]}
    if final:
        unit = next(unit for unit in packet["evidence"] if "mortality was reduced by 25%" in unit["text"])
        value["quotes"] = [{"evidence_id": unit["id"], "quote": unit["text"]}]
    return value


async def validate(output):
    output.mkdir(parents=True, exist_ok=False)
    refs = output / "refs"
    refs.mkdir()
    source = refs / "study.txt"
    fixture = Path(__file__).resolve().parents[1] / "docs/examples/local_followup_refs/study.txt"
    shutil.copyfile(fixture, source)
    rejected = []
    with (output / "transcript.jsonl").open("x", encoding="utf-8") as log:
        async with server(output, output) as session:
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert {"prepare_local_claim_review", "follow_up_local_claim", "generate_claim_review_report"} <= names
            prompt = await session.get_prompt("review_claim_workflow", {
                "claim": "The treatment reduced mortality by 25% at six months.",
                "citation": "Synthetic Local Follow-up Study", "refs_dir": str(refs),
                "output_path": str(output / "review.html")})
            prompt_data = prompt.model_dump(mode="json")
            (output / "workflow_prompt.json").write_text(json.dumps(prompt_data, ensure_ascii=False, indent=2), encoding="utf-8")
            assert all(name in json.dumps(prompt_data) for name in (
                "prepare_local_claim_review", "follow_up_local_claim", "generate_claim_review_report"))

            async def reject(name, arguments):
                try:
                    await call(session, name, arguments, log)
                except ValueError as exc:
                    rejected.append({"tool": name, "reason": str(exc)})
                else:
                    raise AssertionError(f"Invalid request was accepted: {name}")

            first = await call(session, "prepare_local_claim_review", {
                "claim": "The treatment reduced mortality by 25% at six months.",
                "citation_str_or_doi": "Synthetic Local Follow-up Study", "refs_dir": str(refs)}, log)
            first = await complete_packet(session, first, log)
            before = await call(session, "record_claim_review", {"packet_id": first["packet_id"],
                "expected_packet_sha256": first["packet_sha256"], "judgment": fixture_judgment(first)}, log)
            request = {"review_id": before["review_id"], "expected_review_sha256": before["review_sha256"]}
            await reject("follow_up_local_claim", {**request, "expected_review_sha256": "0" * 64})
            second = await complete_packet(session, await call(session, "follow_up_local_claim", request, log), log)
            assert second["local_review"]["retrieval_status"] == "ADDED"
            assert second["evidence"][:len(first["evidence"])] == first["evidence"]
            final = fixture_judgment(second, final=True)
            after = await call(session, "record_claim_review", {"packet_id": second["packet_id"],
                "expected_packet_sha256": second["packet_sha256"], "judgment": final}, log)
            report = await call(session, "generate_claim_review_report", {"review_ids": [after["review_id"]],
                               "output_path": str(output / "review.html")}, log)
            await reject("follow_up_local_claim", request)
            await reject("generate_claim_review_report", {"review_ids": [after["review_id"]], "output_path": str(source)})
            source.write_text(source.read_text(encoding="utf-8").replace("25%", "5%"), encoding="utf-8")
            await reject("record_claim_review", {"packet_id": second["packet_id"],
                         "expected_packet_sha256": second["packet_sha256"], "judgment": final})
            await call(session, "generate_claim_review_report", {"review_ids": [after["review_id"]],
                       "output_path": str(output / "changed_source.html")}, log)
            assert "CHANGED" in (output / "changed_source.html").read_text(encoding="utf-8")
    result = {"type": "scripted_engineering_validation_not_model_effectiveness", "tools": len(names),
              "recorded_judgments": 2, "lookup_status": second["local_review"]["retrieval_status"],
              "added_units": len(second["local_review"]["added_evidence_ids"]),
              "rejected_invalid_requests": rejected, "report": report,
              "offline_boundary_attempts": json.loads((output / "boundary_attempts.json").read_bytes()),
              "model_calls": 0}
    (output / "validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(asyncio.run(validate(parser.parse_args().output.resolve())), ensure_ascii=False))
