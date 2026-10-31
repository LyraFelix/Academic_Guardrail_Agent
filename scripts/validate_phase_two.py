"""Replay the synthetic demo through service and real MCP stdio, without HTTP/models.

Run from the repository with its dependencies installed:
    python scripts/validate_phase_two.py --output-dir <new-directory>
"""

import argparse
import asyncio
from contextlib import ExitStack
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from academic_guardrail.core.reporter import ReportGenerator
from academic_guardrail.core.service import AuditService

ROOT = Path(__file__).resolve().parents[1]
GUARDS = (
    "academic_guardrail.core.service.ChineseAcademicProvider",
    "httpx.AsyncClient.send",
    "academic_guardrail.core.semantic_matcher.SemanticMatcher._get_model",
)

# The transport invokes the real server main. Guards are test instrumentation,
# not replacements for the parser, service, formatter or MCP protocol.
CHILD = r'''
import json, sys
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from academic_guardrail.mcp_server import main
attempts = []
def forbidden(name):
    def stop(*args, **kwargs):
        attempts.append(name)
        raise AssertionError("Offline boundary crossed: " + name)
    return stop
try:
    with ExitStack() as stack:
        for name in json.loads(sys.argv[2]):
            stack.enter_context(patch(name, side_effect=forbidden(name)))
        main()
finally:
    Path(sys.argv[1]).write_text(json.dumps(attempts), encoding="utf-8")
'''


class ResourceCheck(HTMLParser):
    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        assert not any(key in attributes for key in ("src", "srcset", "poster", "action"))
        if "href" in attributes:
            assert tag == "a" and attributes["href"].startswith("https://doi.org/")


async def validate(destination: Path):
    manuscript = ROOT / "docs/examples/phase_two_manuscript.md"
    references = ROOT / "docs/examples/phase_two_refs"
    attempts = []

    def stop(*args, **kwargs):
        attempts.append("offline_boundary_crossed")
        raise AssertionError("Offline execution attempted HTTP provider/send or model access")

    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {"RETRACTION_DB_PATH": ":memory:"}))
        for name in GUARDS:
            stack.enter_context(patch(name, side_effect=stop))
        service = AuditService(offline=True)
        try:
            report = await service.audit_document(str(manuscript), str(references))
        finally:
            await service.close()
    assert not attempts
    assert (report.total_references, report.total_occurrences, report.total_citations) == (1, 3, 3)
    assert len({result.claim.occurrence_id for result in report.results}) == 3
    assert report.results[-1].evidence_status == "PARSE_INCOMPLETE"
    assert any(d.code == "UNRESOLVED_CITATION" for d in report.parse_diagnostics)
    for result in report.results[:2]:
        assert result.text_source == "LOCAL_FULLTEXT"
        location = result.evidence_location
        assert location is not None
        text = Path(location.file_path).read_text(encoding="utf-8-sig")
        assert text[location.char_start:location.char_end] == result.evidence_text
    destination.joinpath("report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    generator = ReportGenerator()
    destination.joinpath("report.html").write_text(generator.generate_html(report), encoding="utf-8")
    destination.joinpath("report.md").write_text(generator.generate_markdown(report), encoding="utf-8")
    guard_path = destination / "mcp_boundary_attempts.json"
    params = StdioServerParameters(
        command=sys.executable, args=["-X", "utf8", "-c", CHILD, str(guard_path), json.dumps(GUARDS)],
        env={**os.environ, "RETRACTION_DB_PATH": ":memory:", "PYTHONDONTWRITEBYTECODE": "1"})
    transcripts = {}
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listing = await session.list_tools()
            calls = [
                ("verify_single_citation", {"citation_str_or_doi": "10.1038/nature12968", "offline": True}, "CONFIRMED"),
                ("check_paper_retraction", {"doi": "10.1234/unknown", "offline": True}, "NO_RECORD"),
                ("audit_document_claims", {"file_path": str(manuscript), "refs_dir": str(references), "output_html_path": str(destination / "mcp_report.html"), "offline": True}, "UNRESOLVED_CITATION"),
                ("generate_audit_html_report", {"file_path": str(manuscript), "refs_dir": str(references), "output_path": str(destination / "mcp_generated.html"), "offline": True}, "正文引用次数: 3"),
            ]
            for name, arguments, expected in calls:
                result = await session.call_tool(name, arguments)
                text = "\n".join(block.text for block in result.content if hasattr(block, "text"))
                assert not result.isError and expected in text, text
                transcripts[name] = text
    assert guard_path.is_file(), "MCP child did not finish and save boundary counters"
    assert json.loads(guard_path.read_text(encoding="utf-8")) == []
    for path in destination.glob("*.html"):
        ResourceCheck().feed(path.read_text(encoding="utf-8"))
    destination.joinpath("mcp_transcript.json").write_text(json.dumps(transcripts, ensure_ascii=False, indent=2), encoding="utf-8")
    evidence = {"validation": "synthetic_offline_engineering", "transport": "stdio",
                "tools": [tool.name for tool in listing.tools], "called_tools": list(transcripts),
                "counts": {"references": 1, "occurrences": 3, "results": 3},
                "forbidden_boundary_attempts": 0, "local_excerpt_round_trip": True,
                "html_external_active_resources": 0, "live_model_requests": 0}
    destination.joinpath("validation.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    # Refuse reuse: an earlier run's artifacts must remain intact.
    destination.mkdir(parents=True, exist_ok=False)
    asyncio.run(validate(destination))


if __name__ == "__main__":
    main()
