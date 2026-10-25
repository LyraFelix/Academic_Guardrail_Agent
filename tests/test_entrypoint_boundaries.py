"""Public entry points must expose the same conservative reference decision."""
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from academic_guardrail.cli import main


AMBIGUOUS = {"matched": True, "is_uncertain": True, "is_retracted": True,
             "title": "Candidate paper", "confidence": 0.9}


def test_cli_uses_shared_ambiguity_decision():
    with patch("academic_guardrail.core.service.AuditService._collect_evidence", AsyncMock(return_value=AMBIGUOUS)):
        result = CliRunner().invoke(main, ["verify", "Example paper"])
    assert result.exit_code == 0, result.output
    assert "UNVERIFIED" in result.output
    assert "AMBIGUOUS" in result.output
    assert "CONFIRMED" not in result.output


def test_cli_offline_unknown_doi_is_explicit():
    with patch("academic_guardrail.core.service.ChineseAcademicProvider", side_effect=AssertionError("HTTP initialized")):
        result = CliRunner().invoke(main, ["verify", "10.1234/unknown", "--offline"])
    assert result.exit_code == 0, result.output
    assert "OFFLINE_NO_MATCH" in result.output
    assert "NO_RECORD" in result.output


@pytest.mark.asyncio
async def test_mcp_uses_shared_ambiguity_decision():
    pytest.importorskip("mcp.server.fastmcp")
    from academic_guardrail import mcp_server

    with patch("academic_guardrail.core.service.AuditService._collect_evidence", AsyncMock(return_value=AMBIGUOUS)):
        result = await mcp_server.verify_single_citation("Example paper")
    assert "UNVERIFIED" in result
    assert "AMBIGUOUS" in result
    assert "CONFIRMED" not in result


@pytest.mark.asyncio
async def test_mcp_offline_retraction_does_not_assert_normal():
    pytest.importorskip("mcp.server.fastmcp")
    from academic_guardrail import mcp_server

    with patch("academic_guardrail.core.service.ChineseAcademicProvider", side_effect=AssertionError("HTTP initialized")):
        unknown = await mcp_server.check_paper_retraction("10.1234/unknown", offline=True)
        known = await mcp_server.verify_single_citation("10.1038/nature12968", offline=True)
    assert "NO_RECORD" in unknown
    assert "状态正常" not in unknown
    assert "CONFIRMED" in known
    assert "offline_database" in known


def test_cli_empty_audit_still_saves_report(tmp_path):
    manuscript = tmp_path / "empty.md"
    manuscript.write_text("No citations here.", encoding="utf-8")
    report = tmp_path / "report.html"
    result = CliRunner().invoke(main, ["audit", str(manuscript), "--offline", "-o", str(report)])
    assert result.exit_code == 0, result.output
    assert report.exists()
    assert "未提取到引用" in report.read_text(encoding="utf-8")


def test_cli_cannot_overwrite_manuscript(tmp_path):
    manuscript = tmp_path / "paper.md"
    content = "Demo [1].\n\n[1] 10.1038/nature12968\n"
    manuscript.write_text(content, encoding="utf-8")
    result = CliRunner().invoke(main, ["audit", str(manuscript), "--offline", "-o", str(manuscript)])
    assert result.exit_code != 0
    assert manuscript.read_text(encoding="utf-8") == content
