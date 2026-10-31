"""Real files validate extraction order and recoverable source coordinates."""

from academic_guardrail.core.parser import DocumentParser
from academic_guardrail.core.ref_store import LocalRefStore


def test_pdf_page_numbers_are_metadata_and_blank_pages_remain_numbered(tmp_path, make_text_pdf):
    from academic_guardrail.core.pdf_extractor import PDFTextExtractor
    path = make_text_pdf(tmp_path / "paper.pdf", [
        "A randomized clinical trial\nAlice Smith\n2024\nAbstract: A short overview.",
        "", "Treatment improves survival in the trial population."])
    pages = PDFTextExtractor.extract_pages(str(path))
    assert len(pages) == 3
    assert not pages[1].strip()
    assert "--- Page" not in PDFTextExtractor.extract(str(path))
    store = LocalRefStore(str(tmp_path))
    record = store.records[0]
    assert record.title == "A randomized clinical trial"
    passage = next(p for p in record.passages if "Treatment improves" in p.text)
    assert passage.location.page == 3
    assert record.fulltext[passage.location.char_start:passage.location.char_end] == passage.text
    assert any(d.code == "EMPTY_PDF_PAGE" for d in store.diagnostics)


def test_pdf_manuscript_occurrence_points_to_physical_page(tmp_path, make_text_pdf):
    path = make_text_pdf(tmp_path / "manuscript.pdf", [
        "First claim [1].", "Opposite claim [1].\nReferences\n[1] Smith. A clinical trial[J]. 2024."])
    parsed = DocumentParser().parse(str(path))
    assert [c.location.page for c in parsed.occurrences] == [1, 2]
    assert parsed.citations[0].location.page == 2


def test_docx_table_is_read_in_body_order(tmp_path):
    from docx import Document
    doc = Document()
    doc.add_paragraph("Before table [1].")
    doc.add_table(rows=1, cols=1).cell(0, 0).text = "Inside table [1]."
    doc.add_paragraph("After table [1].")
    doc.add_paragraph("References")
    doc.add_paragraph("[1] Smith. A clinical trial[J]. 2024.")
    path = tmp_path / "table.docx"
    doc.save(str(path))
    parsed = DocumentParser().parse(str(path))
    assert [c.claim_sentence for c in parsed.occurrences] == ["Before table [1].", "Inside table [1].", "After table [1]."]
    assert all(c.location.page is None for c in parsed.occurrences)


def test_invalid_local_file_is_reported_instead_of_silently_skipped(tmp_path):
    (tmp_path / "broken.pdf").write_bytes(b"not a pdf")
    store = LocalRefStore(str(tmp_path))
    assert not store.records
    assert any(d.code == "LOCAL_FILE_UNREADABLE" for d in store.diagnostics)
