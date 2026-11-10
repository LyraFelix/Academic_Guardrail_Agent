"""A follow-up reads the pinned bytes and returns exact, contextual passages."""

import hashlib
from pathlib import Path

import pytest

from academic_guardrail.core.ref_store import LocalRefStore
from academic_guardrail.core.text_extraction import read_document


TITLE = "A local treatment study"


def paper_text(body: str) -> str:
    return (f"{TITLE}\nAlice Smith\n2024\ndoi: 10.1234/local\n\n"
            "Abstract: This study describes the trial design.\n\n"
            f"Results\n{body}\n\nReferences\n"
            "[1] Other study. Bibliography-only marker zebrafish. 2020.")


def write_paper(tmp_path, body: str):
    path = tmp_path / "paper.txt"
    path.write_text(paper_text(body), encoding="utf-8")
    return path, LocalRefStore(str(tmp_path)).records[0]


@pytest.mark.parametrize("suffix", [".txt", ".pdf", ".docx"])
def test_record_hashes_the_same_bytes_it_extracts(tmp_path, make_text_pdf, monkeypatch, suffix):
    path = tmp_path / f"paper{suffix}"
    text = paper_text("At day 42, the treatment group had 14 responses.")
    if suffix == ".pdf":
        make_text_pdf(path, [text])
    elif suffix == ".docx":
        from docx import Document
        doc = Document()
        for line in text.splitlines():
            doc.add_paragraph(line)
        doc.save(str(path))
    else:
        path.write_text(text, encoding="utf-8")
    original_bytes = path.read_bytes()
    original_text = read_document(str(path)).text
    real_read_bytes = Path.read_bytes

    def replace_after_read(selected_path):
        data = real_read_bytes(selected_path)
        if selected_path == path:
            path.write_bytes(b"Changed after the original read.")
        return data

    monkeypatch.setattr(Path, "read_bytes", replace_after_read)
    record = LocalRefStore(str(tmp_path)).records[0]
    assert getattr(record, "source_sha256", None) == hashlib.sha256(original_bytes).hexdigest()
    assert record.fulltext == original_text


def test_body_result_keeps_neighboring_counterevidence_and_exact_locations(tmp_path):
    from academic_guardrail.core.local_evidence import snapshot_for_record, search_local_evidence

    path, record = write_paper(tmp_path,
        "The enrolled adults had stable baseline measurements.\n\n"
        "At day 42, the treatment group had 14 responses.\n\n"
        "However, this difference was not statistically significant.")
    source = snapshot_for_record(record, str(tmp_path))
    result = search_local_evidence(source, ["14 responses", "day 42"])
    assert "14 responses" not in record.abstract
    assert result.query_terms == ["14 responses", "day 42"]
    assert any("14 responses" in passage.text for passage in result.passages)
    assert any("not statistically significant" in passage.text for passage in result.passages)
    assert any("baseline measurements" in passage.text for passage in result.passages)
    assert not any("Bibliography-only" in passage.text for passage in result.passages)
    starts = []
    for passage in result.passages:
        loc = passage.location
        assert loc.file_path == str(path)
        assert record.fulltext[loc.char_start:loc.char_end] == passage.text
        starts.append(loc.char_start)
    assert starts == sorted(set(starts))


def test_no_match_does_not_expand_aliases_or_search_bibliography(tmp_path):
    from academic_guardrail.core.local_evidence import snapshot_for_record, search_local_evidence

    _, record = write_paper(tmp_path, "Interleukin 6 was measured in plasma.")
    source = snapshot_for_record(record, str(tmp_path))
    for query in (["IL-6"], ["zebrafish"], ["absent endpoint"]):
        result = search_local_evidence(source, query)
        assert result.passages == []
        assert result.matched_passages == 0
        assert result.total_passages > 0


def test_numeric_terms_are_not_substrings_of_other_numbers(tmp_path):
    from academic_guardrail.core.local_evidence import snapshot_for_record, search_local_evidence

    _, record = write_paper(tmp_path, "We enrolled 142 adults; the mean value was 42.5.")
    source = snapshot_for_record(record, str(tmp_path))
    assert search_local_evidence(source, ["42"]).passages == []
    assert search_local_evidence(source, ["42.5"]).passages


def test_chinese_literal_matches_unsegmented_text_with_counterevidence(tmp_path):
    from academic_guardrail.core.local_evidence import snapshot_for_record, search_local_evidence

    sentence = "治疗组死亡率降低25%，但该变化不显著。"
    _, record = write_paper(tmp_path, sentence)
    result = search_local_evidence(snapshot_for_record(record, str(tmp_path)), ["死亡率"])
    assert result.matched_passages == 1
    hit = next(passage for passage in result.passages if sentence in passage.text)
    assert record.fulltext[hit.location.char_start:hit.location.char_end] == hit.text


@pytest.mark.parametrize("term", ["IL6", "死亡率", "IL6死亡率", "25", "25%", "降低25%"])
def test_latin_and_numeric_terms_match_beside_chinese_characters(tmp_path, term):
    from academic_guardrail.core.local_evidence import snapshot_for_record, search_local_evidence

    _, record = write_paper(tmp_path, "治疗组IL6死亡率降低25%但该变化不显著。")
    result = search_local_evidence(snapshot_for_record(record, str(tmp_path)), [term])
    assert result.matched_passages == 1
    assert any("不显著" in passage.text for passage in result.passages)


@pytest.mark.parametrize("text, term", [
    ("治疗组forearm测量结果。", "arm"),
    ("治疗组arm2测量结果。", "arm"),
    ("治疗组_arm测量结果。", "arm"),
    ("治疗组éarm测量结果。", "arm"),
    ("治疗组IL60测量结果。", "IL6"),
    ("死亡率降低125%。", "25%"),
    ("死亡率降低0.25%。", "25%"),
    ("死亡率降低25.5%。", "25"),
    ("该值达到1,025。", "25"),
    ("死亡率降低25％。", "25%"),
])
def test_chinese_context_retains_word_number_and_literal_symbol_boundaries(tmp_path, text, term):
    from academic_guardrail.core.local_evidence import snapshot_for_record, search_local_evidence

    _, record = write_paper(tmp_path, text)
    result = search_local_evidence(snapshot_for_record(record, str(tmp_path)), [term])
    assert result.matched_passages == 0
    assert result.passages == []


def test_query_punctuation_is_literal_not_regular_expression(tmp_path):
    from academic_guardrail.core.local_evidence import snapshot_for_record, search_local_evidence

    _, record = write_paper(tmp_path, "Group AxB received treatment. Marker A.*B was absent.")
    source = snapshot_for_record(record, str(tmp_path))
    assert search_local_evidence(source, ["A.*B"]).passages
    assert search_local_evidence(source, ["A.+B"]).passages == []


def test_overlapping_context_is_deduplicated_and_order_is_deterministic(tmp_path):
    from academic_guardrail.core.local_evidence import snapshot_for_record, search_local_evidence

    _, record = write_paper(tmp_path,
        "The low-dose arm had one response.\n\n"
        "The high-dose arm had two responses.\n\n"
        "Neither arm improved survival.\n\n"
        "A separate cohort was described.")
    source = snapshot_for_record(record, str(tmp_path))
    first = search_local_evidence(source, ["arm"])
    second = search_local_evidence(source, ["arm"])
    assert first == second
    coordinates = [(p.location.char_start, p.location.char_end) for p in first.passages]
    assert len(coordinates) == len(set(coordinates))
    assert coordinates == sorted(coordinates)
    assert first.matched_passages == 3
    assert sum(len(p.text) for p in first.passages) <= 18000


def test_top_ranked_hit_uses_literal_term_coverage_before_document_order(tmp_path):
    from academic_guardrail.core.local_evidence import snapshot_for_record, search_local_evidence

    _, record = write_paper(tmp_path,
        "The response was evaluated.\n\n"
        "An unrelated earlier paragraph.\n\n"
        "A separate middle paragraph.\n\n"
        "The response at day 42 was unchanged.\n\n"
        "This does not support the proposed improvement.")
    result = search_local_evidence(snapshot_for_record(record, str(tmp_path)),
                                   ["response", "day 42"], max_hits=1)
    assert any("response at day 42" in p.text for p in result.passages)
    assert not any("response was evaluated" in p.text for p in result.passages)


@pytest.mark.parametrize("query", [[], [" "], ["arm", "ARM"], ["x" * 101],
                                   ["*"], [1], "arm", ["arm"] * 7])
def test_malformed_queries_are_rejected(tmp_path, query):
    from academic_guardrail.core.local_evidence import snapshot_for_record, search_local_evidence

    _, record = write_paper(tmp_path, "The treatment arm improved.")
    with pytest.raises(ValueError):
        search_local_evidence(snapshot_for_record(record, str(tmp_path)), query)


def test_changed_and_missing_source_block_lookup(tmp_path):
    from academic_guardrail.core.local_evidence import (
        ensure_current_source, snapshot_for_record, source_status, search_local_evidence,
    )

    path, record = write_paper(tmp_path, "The treatment arm improved.")
    source = snapshot_for_record(record, str(tmp_path))
    assert source_status(source) == "CURRENT"
    path.write_text(paper_text("The treatment arm did not improve."), encoding="utf-8")
    assert source_status(source) == "CHANGED"
    with pytest.raises(ValueError, match="CHANGED"):
        search_local_evidence(source, ["treatment"])
    with pytest.raises(ValueError, match="CHANGED"):
        ensure_current_source(source)
    path.unlink()
    assert source_status(source) == "MISSING"
    with pytest.raises(ValueError, match="MISSING"):
        search_local_evidence(source, ["treatment"])


def test_change_after_indexing_cannot_be_snapshotted(tmp_path):
    from academic_guardrail.core.local_evidence import snapshot_for_record

    path, record = write_paper(tmp_path, "The treatment arm improved.")
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="CHANGED"):
        snapshot_for_record(record, str(tmp_path))


def test_snapshot_rejects_outside_root_and_unbound_legacy_record(tmp_path):
    from academic_guardrail.core.local_evidence import snapshot_for_record

    _, record = write_paper(tmp_path, "The treatment arm improved.")
    other_root = tmp_path / "allowed"
    other_root.mkdir()
    with pytest.raises(ValueError, match="outside"):
        snapshot_for_record(record, str(other_root))
    legacy = record.model_copy(update={"source_sha256": None})
    with pytest.raises(ValueError, match="snapshot|hash"):
        snapshot_for_record(legacy, str(tmp_path))


def test_extracted_text_hash_mismatch_blocks_lookup(tmp_path):
    from academic_guardrail.core.local_evidence import snapshot_for_record, search_local_evidence

    _, record = write_paper(tmp_path, "The treatment arm improved.")
    source = snapshot_for_record(record, str(tmp_path)).model_copy(update={"text_sha256": "0" * 64})
    with pytest.raises(ValueError, match="text|extraction"):
        search_local_evidence(source, ["treatment"])


def test_raw_byte_change_is_detected_even_when_extracted_text_is_identical(tmp_path):
    from academic_guardrail.core.local_evidence import snapshot_for_record, source_status

    path, record = write_paper(tmp_path, "The treatment arm improved.")
    source = snapshot_for_record(record, str(tmp_path))
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    assert read_document(str(path)).text == record.fulltext
    assert source_status(source) == "CHANGED"


def test_missing_pinned_file_does_not_switch_to_another_matching_paper(tmp_path):
    from academic_guardrail.core.local_evidence import snapshot_for_record, search_local_evidence

    path, record = write_paper(tmp_path, "The treatment arm improved.")
    source = snapshot_for_record(record, str(tmp_path))
    path.rename(tmp_path / "another_matching_paper.txt")
    with pytest.raises(ValueError, match="MISSING"):
        search_local_evidence(source, ["treatment"])


@pytest.mark.parametrize("max_hits", [0, 4, 1.5, True])
def test_lookup_cannot_expand_the_hit_limit(tmp_path, max_hits):
    from academic_guardrail.core.local_evidence import snapshot_for_record, search_local_evidence

    _, record = write_paper(tmp_path, "The treatment arm improved.")
    with pytest.raises(ValueError, match="max_hits"):
        search_local_evidence(snapshot_for_record(record, str(tmp_path)),
                              ["treatment"], max_hits=max_hits)


def test_unreadable_source_has_explicit_status(tmp_path, monkeypatch):
    from academic_guardrail.core.local_evidence import snapshot_for_record, source_status

    path, record = write_paper(tmp_path, "The treatment arm improved.")
    source = snapshot_for_record(record, str(tmp_path))
    real_read_bytes = Path.read_bytes

    def blocked_read(selected_path):
        if selected_path == path:
            raise PermissionError("Access denied for this test")
        return real_read_bytes(selected_path)

    monkeypatch.setattr(Path, "read_bytes", blocked_read)
    assert source_status(source) == "UNREADABLE"


def test_pdf_followup_preserves_physical_page_coordinates(tmp_path, make_text_pdf):
    from academic_guardrail.core.local_evidence import snapshot_for_record, search_local_evidence

    path = make_text_pdf(tmp_path / "paper.pdf", [
        f"{TITLE}\nAlice Smith\n2024\nAbstract: The trial design is described.",
        "", "Results\nAt day 42, the treatment arm had 14 responses.",
        "However, the difference was not statistically significant."])
    record = LocalRefStore(str(tmp_path)).records[0]
    result = search_local_evidence(snapshot_for_record(record, str(tmp_path)), ["14 responses"])
    hit = next(p for p in result.passages if "14 responses" in p.text)
    assert hit.location.page == 3
    assert hit.location.file_path == str(path)
    assert any(p.location.page == 4 and "not statistically" in p.text for p in result.passages)


def test_docx_followup_uses_original_table_text_and_coordinates(tmp_path):
    from docx import Document
    from academic_guardrail.core.local_evidence import snapshot_for_record, search_local_evidence

    path = tmp_path / "paper.docx"
    doc = Document()
    for line in paper_text("Methods are described here.").split("\n\nReferences")[0].splitlines():
        doc.add_paragraph(line)
    doc.add_paragraph("")
    doc.add_table(rows=1, cols=1).cell(0, 0).text = "At day 42, the treatment arm had 14 responses."
    doc.add_paragraph("")
    doc.add_paragraph("However, the comparison did not reach significance.")
    doc.add_paragraph("References")
    doc.add_paragraph("[1] A different study. Bibliography-only marker zebrafish.")
    doc.save(str(path))
    record = LocalRefStore(str(tmp_path)).records[0]
    result = search_local_evidence(snapshot_for_record(record, str(tmp_path)), ["14 responses"])
    assert any("14 responses" in p.text for p in result.passages)
    assert any("did not reach significance" in p.text for p in result.passages)
    for passage in result.passages:
        assert passage.location.page is None
        assert passage.location.file_path == str(path)
        assert record.fulltext[passage.location.char_start:passage.location.char_end] == passage.text
        assert "zebrafish" not in passage.text
