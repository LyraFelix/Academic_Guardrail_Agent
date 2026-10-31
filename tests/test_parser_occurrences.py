"""User-visible parsing contracts, including cases lost by the old parser."""

import pytest

from academic_guardrail.core.parser import DocumentParser


def parse_file(tmp_path, text, suffix=".md"):
    path = tmp_path / ("manuscript" + suffix)
    path.write_text(text, encoding="utf-8")
    return DocumentParser().parse(str(path)), path


def test_repeated_claims_have_distinct_occurrences_and_exact_marker_offsets(tmp_path):
    text = "治疗有效 [1]。治疗无效 [1]。\n参考文献\n[1] 张三. 临床试验报告[J]. 2024."
    parsed, path = parse_file(tmp_path, text)
    assert len(parsed.citations) == 1
    assert [c.claim_sentence for c in parsed.occurrences] == ["治疗有效 [1]。", "治疗无效 [1]。"]
    assert len({c.occurrence_id for c in parsed.occurrences}) == 2
    for claim in parsed.occurrences:
        assert claim.citation_id == "cit_1"
        assert claim.location.file_path == str(path)
        assert text[claim.location.char_start:claim.location.char_end] == "[1]"


def test_wrapped_reference_without_type_tag_parses_title_and_authors(tmp_path):
    parsed, _ = parse_file(tmp_path, "A claim [1].\nReferences\n[1] Smith J, Doe A. Deep Learning\nfor Clinical Studies. Journal, 2024.\ndoi: 10.1234/example(2023).")
    citation = parsed.citations[0]
    assert citation.title == "Deep Learning for Clinical Studies"
    assert citation.authors == ["Smith J", "Doe A"]
    assert citation.doi == "10.1234/example(2023)"
    assert len(parsed.citations) == len(parsed.occurrences) == 1
    assert "\nfor Clinical" in citation.raw_text


def test_uncited_bibliography_is_metadata_only(tmp_path):
    parsed, path = parse_file(tmp_path, "References\n[1] Smith. A clinical study[J]. 2024.")
    assert len(parsed.citations) == 1
    assert parsed.occurrences == []
    assert DocumentParser().parse_document(str(path))[0][1] is None


def test_ranges_are_expanded_and_unknown_reference_is_reported(tmp_path):
    parsed, _ = parse_file(tmp_path, "A claim [1, 3–4].\nReferences\n[1] Alice. First paper[J]. 2020.\n[3] Bob. Third paper[J]. 2021.")
    assert [c.citation_id for c in parsed.occurrences] == ["cit_1", "cit_3", "cit_4"]
    assert parsed.citations[-1].parse_status == "MISSING"
    assert "UNRESOLVED_CITATION" in {d.code for d in parsed.diagnostics}


def test_masking_preserves_offsets_and_does_not_create_claims(tmp_path):
    text = "```python\n[1] not a reference\n```\n$x=[1]$\nReal claim [1].\nReferences\n[1] Smith. A useful paper[J]. 2024."
    parsed, _ = parse_file(tmp_path, text)
    assert len(parsed.occurrences) == 1
    assert parsed.occurrences[0].location.char_start == text.index("[1]", text.index("Real claim"))


def test_duplicate_bibliography_key_cannot_silently_choose_one(tmp_path):
    parsed, _ = parse_file(tmp_path, "Claim [1].\nReferences\n[1] Alice. Paper one[J]. 2024.\n[1] Bob. Paper two[J]. 2023.")
    assert len(parsed.citations) == 1
    assert parsed.citations[0].parse_status == "AMBIGUOUS"
    assert "DUPLICATE_REFERENCE_KEY" in {d.code for d in parsed.diagnostics}


def test_bibtex_nested_braces_quotes_and_literal_authors(tmp_path):
    text = '@article{trial, title = {A {Nested} Clinical Study}, author = "Smith, Jane and Doe, John", year = {2024}, doi = {10.1234/example(2023)}}'
    parsed, _ = parse_file(tmp_path, text, ".bib")
    assert len(parsed.citations) == 1
    citation = parsed.citations[0]
    assert citation.id == "cit_trial"
    assert citation.title == "A Nested Clinical Study"
    assert citation.authors == ["Smith, Jane", "Doe, John"]
    assert citation.year == 2024
    assert citation.doi == "10.1234/example(2023)"
    assert parsed.occurrences == []


def test_latex_bibitem_keeps_each_cite_command(tmp_path):
    text = r"""First result \cite{trial}. Opposite result \citep[see][p. 2]{trial}.
% ignored \cite{ghost}
\begin{thebibliography}{9}
\bibitem{trial} Smith J. A clinical trial. Journal, 2024.
\end{thebibliography}"""
    parsed, _ = parse_file(tmp_path, text, ".tex")
    assert len(parsed.citations) == 1
    assert [c.citation_id for c in parsed.occurrences] == ["cit_trial", "cit_trial"]
    assert parsed.citations[0].title == "A clinical trial"


def test_latex_relative_bib_and_unresolved_keys(tmp_path):
    (tmp_path / "refs.bib").write_text('@article{one, title={A trial}, year={2024}}', encoding="utf-8")
    parsed, _ = parse_file(tmp_path, r"Result \cite{one,missing}. \bibliography{refs}", ".tex")
    assert parsed.citations[0].title == "A trial"
    assert [c.citation_id for c in parsed.occurrences] == ["cit_one", "cit_missing"]
    assert "UNRESOLVED_CITATION" in {d.code for d in parsed.diagnostics}


def test_unsupported_bibtex_expression_is_visible(tmp_path):
    parsed, _ = parse_file(tmp_path, '@article{one, title=prefix # " Trial", year={2024}}', ".bib")
    assert "UNSUPPORTED_BIBTEX_VALUE" in {d.code for d in parsed.diagnostics}
    assert not parsed.citations[0].title


@pytest.mark.parametrize("target", ["https://example.com/1706.03762", "https://notarxiv.org/abs/1706.03762"])
def test_unknown_urls_do_not_become_arxiv_dois(target):
    from academic_guardrail.core.exceptions import ParserError
    with pytest.raises(ParserError, match="arXiv"):
        DocumentParser().parse_document(target)


@pytest.mark.parametrize("claim", ["Treatment improves\nsurvival [1].", "Treatment improves survival. [1]"])
def test_soft_wrap_and_post_sentence_marker_keep_the_statement(tmp_path, claim):
    parsed, _ = parse_file(tmp_path, claim + "\nReferences\n[1] Smith. A trial[J]. 2024.")
    assert parsed.occurrences[0].claim_sentence == claim


def test_appendix_numbers_are_not_reference_entries(tmp_path):
    parsed, _ = parse_file(tmp_path, "Works [1].\nReferences\n[1] Smith. Trial[J]. 2024.\n# Appendix\n1. First procedure\n2. Second procedure")
    assert len(parsed.citations) == 1
    assert parsed.citations[0].parse_status == "PARSED"


def test_latex_definition_is_not_a_body_occurrence(tmp_path):
    parsed, _ = parse_file(tmp_path, r"\newcommand{\mycite}{\cite{trial}}" + "\n" + r"Result \cite{trial}. \begin{thebibliography}{9}\bibitem{trial} Smith. Trial. 2024.\end{thebibliography}", ".tex")
    assert len(parsed.occurrences) == 1
    assert "newcommand" not in parsed.occurrences[0].claim_sentence
    assert "UNEXPANDED_LATEX" in {d.code for d in parsed.diagnostics}


def test_inline_doi_id_cannot_replace_bibitem_key(tmp_path):
    parsed, path = parse_file(tmp_path, r"Claim \cite{doi_2}. Other result 10.1234/other." + "\n" + r"\begin{thebibliography}{9}\bibitem{doi_2} Smith. Original trial. 2024.\end{thebibliography}", ".tex")
    assert len({citation.id for citation in parsed.citations}) == 2
    first_citation, _ = DocumentParser().parse_document(str(path))[0]
    assert first_citation.title == "Original trial"
    assert first_citation.doi is None


def test_bibtex_grouped_organization_is_one_author(tmp_path):
    parsed, _ = parse_file(tmp_path, '@article{one,title={A study},author={{Research and Development Team} and Smith, Jane},year={2024}}', ".bib")
    assert parsed.citations[0].authors == ["Research and Development Team", "Smith, Jane"]


def test_unsupported_reference_style_cannot_manufacture_doi_body_claim(tmp_path):
    parsed, _ = parse_file(tmp_path, "Body text.\nReferences\nSmith (2024). A trial. doi: 10.1234/trial")
    assert parsed.occurrences == []
    assert "UNSUPPORTED_REFERENCE_STYLE" in {d.code for d in parsed.diagnostics}


def test_adjacent_post_sentence_citations_keep_opposed_claims_separate(tmp_path):
    parsed, _ = parse_file(tmp_path, "Treatment improves survival. [1] Treatment reduces survival. [1]\nReferences\n[1] Smith. Trial[J]. 2024.")
    assert [c.claim_sentence for c in parsed.occurrences] == ["Treatment improves survival. [1]", "Treatment reduces survival. [1]"]
