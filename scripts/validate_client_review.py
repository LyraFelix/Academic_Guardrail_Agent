"""Exercise the real MCP transport with scripted judgments, not model accuracy.

Run from the repository root: python scripts/validate_client_review.py --output-dir <new-dir>
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from validate_phase_two import CHILD, GUARDS


def save(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


async def validate(destination: Path):
    attempts = destination / "boundary_attempts.json"
    env = {**os.environ, "RETRACTION_DB_PATH": ":memory:", "PYTHONDONTWRITEBYTECODE": "1",
           "ACADEMIC_GUARDRAIL_REVIEW_DIR": str(destination / "stored")}
    params = StdioServerParameters(command=sys.executable,
                                   args=["-X", "utf8", "-c", CHILD, str(attempts), json.dumps(GUARDS)], env=env)
    transcript = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listing = await session.list_tools()
            names = {tool.name for tool in listing.tools}
            expected = {"verify_single_citation", "check_paper_retraction", "audit_document_claims",
                        "generate_audit_html_report", "prepare_claim_review", "read_claim_evidence", "record_claim_review"}
            assert names == expected
            save(destination / "tools.json", listing.model_dump(mode="json"))
            prompts = await session.list_prompts()
            assert "review_claim_workflow" in {prompt.name for prompt in prompts.prompts}
            prompt = await session.get_prompt("review_claim_workflow", {"claim": "Treatment reduces mortality by 90%."})
            save(destination / "prompt.json", prompt.model_dump(mode="json"))

            async def call(name, arguments, *, should_fail=False):
                result = await session.call_tool(name, arguments)
                transcript.append({"tool": name, "arguments": arguments, "result": result.model_dump(mode="json")})
                save(destination / "transcript.json", transcript)
                assert bool(result.isError) == should_fail, transcript[-1]
                if should_fail:
                    return None
                return result.structuredContent or json.loads(next(block.text for block in result.content if hasattr(block, "text")))

            source = "Treatment reduces mortality by 10%. " + " ".join(f"Background statement {i}." for i in range(26))
            prepared = await call("prepare_claim_review", {"claim": "Treatment reduces mortality by 90%.",
                                                           "reference_text": source, "offline": True})
            assert prepared["reference_status"] == "PROVIDED_TEXT_NOT_IDENTITY_VERIFIED"
            assert prepared["next_offset"] is not None
            evidence = list(prepared["evidence"])
            following = prepared["next_offset"]
            while following is not None:
                page = await call("read_claim_evidence", {"packet_id": prepared["packet_id"], "offset": following})
                assert page["packet_sha256"] == prepared["packet_sha256"]
                evidence.extend(page["evidence"])
                following = page["next_offset"]
            assert len(evidence) == prepared["total_evidence"] == 27
            judgment = {"conclusion": "CONTRADICTED", "rationale": "The stated percentages differ for the same treatment and outcome.",
                        "reviewed_evidence_ids": [item["id"] for item in evidence],
                        "quotes": [{"evidence_id": "e1", "quote": "Treatment reduces mortality by 10%."}],
                        "checks": {"subject": "Same treatment.", "relation": "Both describe mortality reduction.",
                                   "numbers": "90% differs from 10%.", "scope": "No different population or time is stated.",
                                   "counterevidence": "The remaining sentences are unrelated background."},
                        "client_model": "scripted validation fixture, not an LLM",
                        "suggested_revision": {"text": "Treatment reduces mortality by 10%.",
                                               "evidence_ids": ["e1"], "reason": "Use the source's numerical value."}}
            binding = {"packet_id": prepared["packet_id"], "expected_packet_sha256": prepared["packet_sha256"]}
            saved = await call("record_claim_review", {**binding, "judgment": judgment})
            assert saved["validation_status"] == "EVIDENCE_LINKS_VALID"
            assert saved["semantic_judgment_verified"] is False
            assert saved["judgment"]["conclusion"] == "CONTRADICTED"
            assert saved["judgment"]["suggested_revision"]["evidence_ids"] == ["e1"]
            assert saved["suggested_revision_semantically_verified"] is False
            invented = {**judgment, "quotes": [{"evidence_id": "e1", "quote": "Treatment reduces mortality by 90%."}]}
            await call("record_claim_review", {**binding, "judgment": invented}, should_fail=True)
            await call("record_claim_review", {**binding, "expected_packet_sha256": "0" * 64,
                                                "judgment": judgment}, should_fail=True)
            bad_revision = {**judgment, "suggested_revision": {"text": "Unsupported rewrite.",
                            "evidence_ids": ["e2"], "reason": "Refers to a unit without a submitted quote."}}
            await call("record_claim_review", {**binding, "judgment": bad_revision}, should_fail=True)
            await call("read_claim_evidence", {"packet_id": "../outside"}, should_fail=True)
            blocked = await call("prepare_claim_review", {"claim": "Treatment reduces mortality.",
                                                          "citation_str_or_doi": "10.1038/nature12968", "offline": True})
            assert blocked["reference_status"] == "RETRACTED" and not blocked["evidence"]
            assert "REFERENCE_RETRACTED" in blocked["blocking_reasons"]
    assert json.loads(attempts.read_text(encoding="utf-8")) == []
    assert len(list((destination / "stored").glob("*.review.json"))) == 1
    result = {"validation": "scripted_mcp_workflow_not_llm_accuracy", "mcp_tools": len(names),
              "successful_recorded_judgments": 1, "rejected_invalid_calls": 4,
              "reference_retraction_precedence": True, "paginated_evidence": 27,
              "offline_boundary_attempts": 0, "live_model_requests": 0}
    save(destination / "validation.json", result)
    print(json.dumps(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    destination = parser.parse_args().output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    asyncio.run(validate(destination))


if __name__ == "__main__":
    main()
