"""New data-chain fields must survive CLI/MCP and saved reports."""

import pytest
from click.testing import CliRunner

from academic_guardrail.cli import main
from academic_guardrail.core.reporter import ReportGenerator
from academic_guardrail.core.service import AuditService
from academic_guardrail.core.result_formatter import format_result


@pytest.fixture
def manuscript(tmp_path):
    path = tmp_path / "manuscript.md"
    path.write_text("Treatment improves survival [1]. A missing reference [2].\nReferences\n[1] Smith. A randomized clinical trial[J]. 2024.", encoding="utf-8")
    refs = tmp_path / "refs"
    refs.mkdir()
    (refs / "paper.txt").write_text("A randomized clinical trial\nSmith\n2024\n\nAbstract: A trial.\n\nResults\nTreatment improves survival.", encoding="utf-8")
    return path, refs


@pytest.mark.asyncio
async def test_reports_show_separate_counts_diagnostics_and_positions(manuscript):
    path, refs = manuscript
    service = AuditService(offline=True)
    try:
        report = await service.audit_document(str(path), str(refs))
    finally:
        await service.close()
    for rendered in (ReportGenerator().generate_html(report), ReportGenerator().generate_markdown(report)):
        assert "文献条目" in rendered
        assert "正文引用次数" in rendered
        assert "UNRESOLVED_CITATION" in rendered
        assert "occ_1" in rendered
        assert "LOCAL_FULLTEXT" in rendered
        assert "paper.txt" in rendered
        assert "字符" in rendered
    text = format_result(report.results[0])
    assert "occ_1" in text
    assert "LOCAL_FULLTEXT" in text
    assert "字符" in text


def test_cli_document_output_exposes_parse_diagnostics(manuscript, tmp_path):
    path, refs = manuscript
    output = tmp_path / "report.md"
    result = CliRunner().invoke(main, ["audit", str(path), "--refs-dir", str(refs), "--offline", "-o", str(output)])
    assert result.exit_code == 0, result.output
    assert "UNRESOLVED_CITATION" in result.output
    assert "正文引用次数" in result.output
    assert "UNRESOLVED_CITATION" in output.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_mcp_document_output_exposes_parse_diagnostics(manuscript, tmp_path):
    from academic_guardrail.mcp_server import audit_document_claims
    path, refs = manuscript
    output = tmp_path / "report.html"
    text = await audit_document_claims(str(path), refs_dir=str(refs), output_html_path=str(output), offline=True)
    assert "UNRESOLVED_CITATION" in text
    assert "正文引用次数" in text
    assert "occ_1" in text
    assert output.is_file()


@pytest.mark.asyncio
async def test_new_diagnostics_are_html_escaped(tmp_path):
    path = tmp_path / "unsafe.md"
    path.write_text("Claim [1].\nReferences\n[1] Alice. Trial[J]. 2024.\n[1] <script>alert(1)</script>. Other[J]. 2023.", encoding="utf-8")
    service = AuditService(offline=True)
    try:
        report = await service.audit_document(str(path))
    finally:
        await service.close()
    rendered = ReportGenerator().generate_html(report)
    assert "<script>alert(1)</script>" not in rendered
    assert "DUPLICATE_REFERENCE_KEY" in rendered
    assert "&lt;script&gt;" in rendered
