"""Replay synthetic wording checks and the real offline CLI/MCP entrypoints.

Run: python scripts/validate_phase_three.py --output-dir <new-directory>
This validates software behavior, not scientific correctness or benchmark accuracy.
"""

import argparse
import asyncio
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from academic_guardrail.core.reporter import ReportGenerator
from academic_guardrail.core.service import AuditService
from academic_guardrail.providers.claim_eval import ClaimEvaluator

# Reuse the phase-two transport instrumentation, not its results or assertions.
from validate_phase_two import CHILD, GUARDS, ResourceCheck

ROOT = Path(__file__).resolve().parents[1]
MANUSCRIPT = ROOT / "docs/examples/phase_three_manuscript.md"
REFERENCES = ROOT / "docs/examples/phase_three_refs"
EXPECTED_CODES = ("NUMBER_MISMATCH", "NEGATION_DIFFERENCE", "CAUSAL_OVERSTATEMENT", "SCOPE_STRENGTHENED")


def save_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def replay_cases(destination: Path):
    fixture = json.loads((ROOT / "tests/fixtures/semantic_cases.json").read_text(encoding="utf-8"))
    evaluator = ClaimEvaluator(use_embeddings=False)
    outputs = []
    for case in fixture["cases"]:
        result = evaluator.assess(case["claim"], case["evidence"])
        outputs.append({"id": case["id"], "claim": case["claim"], "evidence": case["evidence"],
                        "expected_state": case["expected_state"], "actual": result.model_dump(mode="json")})
    save_json(destination / "semantic_outputs.json", outputs)
    for case, output in zip(fixture["cases"], outputs):
        assert output["actual"]["state"] == case["expected_state"], case["id"]
        assert set(case["required_codes"]) <= {f["code"] for f in output["actual"]["findings"]}, case["id"]
    return len(outputs)


async def validate(destination: Path):
    attempts = []

    def stop(*args, **kwargs):
        attempts.append("offline_boundary_crossed")
        raise AssertionError("Offline execution attempted provider, HTTP or model access")

    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {"RETRACTION_DB_PATH": ":memory:"}))
        for name in GUARDS:
            stack.enter_context(patch(name, side_effect=stop))
        case_count = replay_cases(destination)
        service = AuditService(offline=True)
        try:
            report = await service.audit_document(str(MANUSCRIPT), str(REFERENCES))
        finally:
            await service.close()
    save_json(destination / "service_boundary_attempts.json", attempts)
    assert not attempts
    save_json(destination / "report.json", report.model_dump(mode="json"))
    generator = ReportGenerator()
    (destination / "report.html").write_text(generator.generate_html(report), encoding="utf-8")
    (destination / "report.md").write_text(generator.generate_markdown(report), encoding="utf-8")
    assert (report.total_references, report.total_occurrences, report.total_citations) == (1, 4, 4)
    assert report.passed_count == 0
    assert report.warning_count == 2 and report.notice_count == 2
    for result, expected in zip(report.results, EXPECTED_CODES):
        assert expected in {f.code for f in result.semantic_findings}, result.model_dump()
        for item in result.semantic_findings:
            location = item.evidence_location
            assert location is not None
            text = Path(location.file_path).read_text(encoding="utf-8-sig")
            assert text[location.char_start:location.char_end] == item.evidence_text

    env = {**os.environ, "RETRACTION_DB_PATH": ":memory:", "PYTHONDONTWRITEBYTECODE": "1", "COLUMNS": "240"}
    # Use the actual CLI main in another process with the same boundary guards.
    cli_child = CHILD.replace("from academic_guardrail.mcp_server import main", "from academic_guardrail.cli import main")
    cli_child = cli_child.replace("        main()", "        main(args=sys.argv[3:])")
    completed = subprocess.run([sys.executable, "-X", "utf8", "-c", cli_child,
                                str(destination / "cli_boundary_attempts.json"), json.dumps(GUARDS),
                                "audit", str(MANUSCRIPT), "--refs-dir", str(REFERENCES), "--offline",
                                "-o", str(destination / "cli_report.html")],
                               env=env, capture_output=True, text=True, encoding="utf-8", timeout=90)
    (destination / "cli_transcript.txt").write_text(completed.stdout + completed.stderr, encoding="utf-8")
    assert completed.returncode == 0, completed.stderr
    assert json.loads((destination / "cli_boundary_attempts.json").read_text(encoding="utf-8")) == []
    cli_html = (destination / "cli_report.html").read_text(encoding="utf-8")
    assert all(code in cli_html for code in EXPECTED_CODES)

    boundary_path = destination / "mcp_boundary_attempts.json"
    params = StdioServerParameters(command=sys.executable,
                                   args=["-X", "utf8", "-c", CHILD, str(boundary_path), json.dumps(GUARDS)], env=env)
    transcripts = {}
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listing = await session.list_tools()
            calls = [
                ("verify_single_citation", {"citation_str_or_doi": "10.1038/nature12968", "offline": True}, ["CONFIRMED"]),
                ("check_paper_retraction", {"doi": "10.1234/unknown", "offline": True}, ["NO_RECORD"]),
                ("audit_document_claims", {"file_path": str(MANUSCRIPT), "refs_dir": str(REFERENCES), "output_html_path": str(destination / "mcp_report.html"), "offline": True}, EXPECTED_CODES),
                ("generate_audit_html_report", {"file_path": str(MANUSCRIPT), "refs_dir": str(REFERENCES), "output_path": str(destination / "mcp_generated.html"), "offline": True}, ["正文引用次数: 4"]),
            ]
            assert {t.name for t in listing.tools} == {name for name, _, _ in calls}
            for name, arguments, expected in calls:
                result = await session.call_tool(name, arguments)
                text = "\n".join(block.text for block in result.content if hasattr(block, "text"))
                transcripts[name] = text
                assert not result.isError and all(item in text for item in expected), text
    save_json(destination / "mcp_transcript.json", transcripts)
    assert json.loads(boundary_path.read_text(encoding="utf-8")) == []
    for path in destination.glob("*.html"):
        content = path.read_text(encoding="utf-8")
        ResourceCheck().feed(content)
        assert all(code in content for code in EXPECTED_CODES), path

    files = sorted((ROOT / "src").rglob("*.py")) + [MANUSCRIPT, REFERENCES / "study.txt", ROOT / "tests/fixtures/semantic_cases.json"]
    evidence = {"validation": "synthetic_offline_engineering", "synthetic_cases": case_count,
                "counts": {"references": 1, "occurrences": 4, "results": 4, "pass": 0, "notice": 2, "warning": 2},
                "mcp_transport": "stdio", "called_tools": list(transcripts), "cli_exit_code": completed.returncode,
                "forbidden_boundary_attempts": 0, "local_excerpt_round_trip": True,
                "html_external_active_resources": 0, "live_model_requests": 0,
                "sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}}
    save_json(destination / "validation.json", evidence)
    print(json.dumps({key: value for key, value in evidence.items() if key != "sha256"}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    destination = parser.parse_args().output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    asyncio.run(validate(destination))


if __name__ == "__main__":
    main()
