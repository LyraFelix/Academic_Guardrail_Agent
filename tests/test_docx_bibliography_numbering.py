"""Use actual Word list definitions, without inserting their labels into the text."""

from io import BytesIO

from docx import Document
from docx.enum.style import WD_STYLE_TYPE

from academic_guardrail.core.parser import DocumentParser
from academic_guardrail.core.text_extraction import read_document


def parse_word(document):
    buffer = BytesIO()
    document.save(buffer)
    path = "numbered_draft.docx"
    return (read_document(path, source_bytes=buffer.getvalue()),
            DocumentParser().parse(path, source_bytes=buffer.getvalue()))


def decimal_list(document, start=None):
    definitions = document.part.numbering_part.element
    style_id = document.styles["List Number"].element.pPr.numPr.numId.val
    instance = definitions.add_num(definitions.num_having_numId(style_id).abstractNumId.val)
    if start is not None:
        instance.add_lvlOverride(ilvl=0).add_startOverride(start)
    return instance.numId


def apply_list(paragraph, num_id, level=0):
    numbering = paragraph._p.get_or_add_pPr().get_or_add_numPr()
    numbering.get_or_add_ilvl().val = level
    numbering.get_or_add_numId().val = num_id


def test_inherited_word_list_uses_displayed_numbers_and_keeps_real_positions():
    document = Document()
    inherited = document.styles.add_style("Numbered References", WD_STYLE_TYPE.PARAGRAPH)
    inherited.base_style = document.styles["List Number"]
    document.add_paragraph("A numbered body item.", style="List Number")
    document.add_paragraph("We compared two methods [2, 3].")
    document.add_paragraph("References")
    first = "Doe. First Method[J]. 2020. doi: 10.1234/first"
    second = "Lee. Second Method[J]. 2021. doi: 10.1234/second"
    document.add_paragraph(first, style="List Number")
    document.add_paragraph(second, style=inherited)
    document.add_paragraph("Appendix")
    document.add_paragraph("A numbered appendix item.", style=inherited)

    source, parsed = parse_word(document)
    assert source.text == "\n".join(p.text for p in document.paragraphs)
    assert [(c.id, c.doi) for c in parsed.citations] == [("cit_2", "10.1234/first"), ("cit_3", "10.1234/second")]
    assert [c.raw_text for c in parsed.citations] == [first, second]
    for citation in parsed.citations:
        assert source.text[citation.location.char_start:citation.location.char_end].strip() == citation.raw_text
    for claim in parsed.occurrences:
        assert source.text[claim.location.char_start:claim.location.char_end] == "[2, 3]"
        assert claim.claim_sentence == "We compared two methods [2, 3]."
    assert not parsed.diagnostics


def test_concrete_list_instances_continue_independently_and_keep_manual_entries():
    document = Document()
    starts_at_five = decimal_list(document, 5)
    starts_at_one = decimal_list(document)
    document.add_paragraph("We compare prior work [5, 1, 6, 8].")
    document.add_paragraph("References")
    for num_id, title in [(starts_at_five, "First Title"), (starts_at_one, "Other Title"),
                          (starts_at_five, "Last Title")]:
        apply_list(document.add_paragraph(f"Doe. {title}[J]. 2024."), num_id)
    document.add_paragraph("[8] Doe. Manually Numbered[J]. 2024.")
    _, parsed = parse_word(document)
    assert [(c.id, c.title) for c in parsed.citations] == [
        ("cit_5", "First Title"), ("cit_1", "Other Title"),
        ("cit_6", "Last Title"), ("cit_8", "Manually Numbered")]


def test_restarted_list_reuses_visible_key_and_reports_ambiguity():
    document = Document()
    document.add_paragraph("We cite prior work [1].")
    document.add_paragraph("References")
    for title in ("Original paper", "Different paper"):
        apply_list(document.add_paragraph(f"Doe. {title}[J]. 2024."), decimal_list(document, 1))
    _, parsed = parse_word(document)
    assert [(c.id, c.parse_status) for c in parsed.citations] == [("cit_1", "AMBIGUOUS")]
    assert "DUPLICATE_REFERENCE_KEY" in {d.code for d in parsed.diagnostics}


def test_word_section_heading_ends_numbered_bibliography_before_a_later_body_list():
    document = Document()
    document.add_paragraph("A result [1].")
    document.add_heading("References", level=1)
    document.add_paragraph("Doe. An Actual Reference[J]. 2024.", style="List Number")
    heading = document.styles.add_style("Supplement Heading", WD_STYLE_TYPE.PARAGRAPH)
    heading.base_style = document.styles["Heading 1"]
    document.add_paragraph("Supplementary procedures", style=heading)
    document.add_paragraph("Follow this procedure.", style="List Number")
    document.add_paragraph("The supplement also cites [1].")
    _, parsed = parse_word(document)
    assert [(c.id, c.raw_text) for c in parsed.citations] == [("cit_1", "Doe. An Actual Reference[J]. 2024.")]
    assert [c.claim_sentence for c in parsed.occurrences] == ["A result [1].", "The supplement also cites [1]."]


def test_unsupported_list_in_bibliography_does_not_supply_a_key_or_merge_into_neighbor():
    document = Document()
    document.add_paragraph("A body bullet.", style="List Bullet")
    document.add_paragraph("Prior results [1, 2, 3].")
    document.add_paragraph("References")
    document.add_paragraph("[1] Doe. Manual Reference[J]. 2024.")
    document.add_paragraph("Unnumbered bibliography bullet.", style="List Bullet")
    apply_list(document.add_paragraph("Unsupported nested level."), decimal_list(document), level=1)
    document.add_paragraph("[3] Doe. Another Reference[J]. 2024.")
    _, parsed = parse_word(document)
    assert parsed.citations[0].raw_text == "[1] Doe. Manual Reference[J]. 2024."
    assert {c.id: c.parse_status for c in parsed.citations} == {"cit_1": "PARSED", "cit_2": "MISSING", "cit_3": "PARSED"}
    diagnostics = [d for d in parsed.diagnostics if d.code == "UNSUPPORTED_DOCX_REFERENCE_NUMBERING"]
    assert [d.location.line for d in diagnostics] == [5, 6]
