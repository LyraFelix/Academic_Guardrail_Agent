"""Exercise real SDK communication; importing handlers alone misses wire errors."""

import io
import json
import os
from pathlib import Path
import sys
import sysconfig

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from academic_guardrail import __version__
from scripts.client_review_batch import call
from scripts.validate_phase_two import CHILD, GUARDS


@pytest.mark.asyncio
@pytest.mark.parametrize("connection", ["initialize", "discover"])
@pytest.mark.parametrize("entrypoint", ["guarded_main", "console_script"])
async def test_stdio_workflow_and_wire_contract(tmp_path, connection, entrypoint):
    """Both existing hosts and modern discovery reach the manuscript and single-claim tools."""
    boundary = tmp_path / "boundary.json"
    command = sys.executable
    args = ["-X", "utf8", "-c", CHILD, str(boundary), json.dumps(GUARDS)]
    if entrypoint == "console_script":
        suffix = ".exe" if sys.platform == "win32" else ""
        executable = Path(sysconfig.get_path("scripts")) / f"academic-guardrail-mcp{suffix}"
        assert executable.is_file(), "Install the project before running transport tests"
        command, args = str(executable), []
    params = StdioServerParameters(
        command=command,
        args=args,
        env={**os.environ, "RETRACTION_DB_PATH": ":memory:",
             "ACADEMIC_GUARDRAIL_REVIEW_DIR": str(tmp_path / "reviews")},
    )
    transcript = io.StringIO()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=30) as session:
            if connection == "initialize":
                await session.initialize()
                assert session.initialize_result is not None
            else:
                await session.discover()
                assert session.discover_result is not None
            assert session.server_info.name == "Academic Guardrail Agent"
            assert session.server_info.version == __version__

            listing = await session.list_tools()
            tools = {tool.name: tool for tool in listing.tools}
            assert set(tools) == {
                "verify_single_citation", "check_paper_retraction",
                "audit_document_claims", "generate_audit_html_report",
                "prepare_claim_review", "read_claim_evidence", "record_claim_review",
                "prepare_local_claim_review", "follow_up_local_claim",
                "generate_claim_review_report",
                "prepare_manuscript_review", "generate_manuscript_review_report",
            }
            required = tools["record_claim_review"].input_schema["required"]
            assert set(required) == {"packet_id", "judgment", "expected_packet_sha256"}
            prompt = await session.get_prompt("review_claim_workflow", {"claim": "A claim."})
            assert "record_claim_review" in prompt.messages[0].content.text

            prepared = await call(session, "prepare_claim_review", {
                "claim": "Treatment reduces mortality by 90%.",
                "reference_text": "Treatment reduces mortality by 10%.",
            }, transcript)
            page = await call(session, "read_claim_evidence", {
                "packet_id": prepared["packet_id"],
            }, transcript)
            assert page["packet_sha256"] == prepared["packet_sha256"]
            assert page["evidence"][0]["text"] == "Treatment reduces mortality by 10%."
            with pytest.raises(ValueError, match="Provide exactly one"):
                await call(session, "prepare_claim_review", {"claim": "A claim."}, transcript)

    # Persisted protocol transcripts retain camelCase, even though SDK attributes
    # are snake_case. These records are also consumed by evaluation/audit scripts.
    responses = [json.loads(line)["response"] for line in transcript.getvalue().splitlines()]
    assert "structuredContent" in responses[0]
    payload = responses[0]["structuredContent"] or json.loads(responses[0]["content"][0]["text"])
    assert payload["packet_id"] == prepared["packet_id"]
    assert responses[-1]["isError"] is True
    assert all("is_error" not in item and "structured_content" not in item for item in responses)
    if entrypoint == "guarded_main":
        assert json.loads(boundary.read_text(encoding="utf-8")) == []
