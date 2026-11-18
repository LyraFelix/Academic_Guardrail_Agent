"""Synthetic source facts exercise lookup mechanics independently of model decisions."""

import pytest

from academic_guardrail.core.local_evidence import select_local_passages
from academic_guardrail.core.models import EvidencePassage, SourceLocation
from academic_guardrail.core.search_view import search_view, whole_term_pattern


def paper(texts, pages=None):
    source = "\n\n".join(texts)
    passages, offset = [], 0
    for i, text in enumerate(texts):
        location = SourceLocation(file_path="paper.txt", page=pages[i] if pages else None,
                                  char_start=offset, char_end=offset + len(text))
        passages.append(EvidencePassage(text=text, source_kind="LOCAL_FULLTEXT", location=location))
        offset += len(text) + 2
    return source, passages


def occurrences(text, term):
    key = search_view(term).text
    pattern = whole_term_pattern(key, normalized=True)
    return [text[a:b] for a, b in search_view(text).spans(pattern)]


@pytest.mark.parametrize(("query", "raw"), [
    ("configuration", "conﬁgura-\ntion"), ("self attention", "self-\nattention"),
    ("semi-supervised reconstruction", "semi-\nsupervised re-\nconstruction"),
    ("fine-tuning", "ﬁne-tune"), ("Model-base", "Model\nbase"),
    ("two-layer MLP", "2-layer MLP"), ("5 by 7", "5 × 7"),
    ("2×3", "two by three"),
    ("Batch Normalization", "BN"), ("BN", "BatchNorm"),
    ("LN", "Layer Normaliza-\ntion"), ("depthwise convolution", "depthwise conv"),
    ("-25%", "−25%"), ("-25%", "- 25%"),
])
def test_normalized_spelling_maps_to_exact_raw_span(query, raw):
    text = f"Before: {raw}; after: {raw}."
    assert occurrences(text, query) == [raw, raw]
    source, passages = paper([text])
    chosen = select_local_passages(passages, [query])
    assert chosen.hit_indices == (0,)
    loc = passages[0].location
    assert source[loc.char_start:loc.char_end] == text
    assert chosen.character_count == len(text)


@pytest.mark.parametrize(("query", "text"), [
    ("25", "−25 or -25 or - 25 or +25 or 25.5 or 0.25 or .25 or 1,025."),
    ("25%", "−25% or 0.25% or -.25% or 125% or 25％."),
    ("-25", "25 or 25.5 or -25.8."), ("2", "twenty-two or two thousand."),
    ("BN", "LayerNorm only."), ("Layer Normalization", "BatchNorm only."),
    ("arm", "forearm, évolution_arm, 中éarm9文."), ("IL-6", "Interleukin 6 was measured."),
    ("arm", "fore-\narm"), ("fore", "fore-\narm"),
    ("Table 1", "Table 10: Measurements."), ("A.+B", "A.*B occurred."),
])
def test_no_seed_for_fragments_unlisted_aliases_or_other_normalization_family(query, text):
    assert not occurrences(text, query)
    _, passages = paper([text])
    for mode in ("normalized", "ranked", "structural"):
        assert select_local_passages(passages, [query], mode=mode).hit_indices == ()


def test_each_normalized_dimension_operand_keeps_its_own_offset():
    assert occurrences("Kernel 5 by 7.", "7") == ["7"]
    assert occurrences("病人IL6降低5%。", "IL6降低5%") == ["IL6降低5%"]


def test_rare_phrase_and_distinct_context_outweigh_repeated_general_term():
    repeated = "The instrument was used. " * 12
    _, passages = paper([repeated, "Background.", repeated, "Details.", repeated,
                         "The porosity limit was exceeded.", "Other methods."])
    query = ["instrument", "porosity limit"]
    assert select_local_passages(passages, query, mode="original").hit_indices == (0, 2, 4)
    ranked = select_local_passages(passages, query, mode="ranked")
    assert ranked.hit_indices[0] == 5
    assert ranked.context_indices == tuple(sorted(set(ranked.context_indices)))


def test_repeated_passage_yields_a_hit_slot_to_different_evidence():
    same = "The velocity calibration was repeated before each measurement."
    _, passages = paper([same, "Unrelated.", same, "Filler.", "The velocity decreased."])
    result = select_local_passages(passages, ["velocity"], mode="ranked", max_hits=2)
    assert set(result.hit_indices) == {0, 4}


def test_equivalent_query_spellings_cannot_double_count_one_occurrence():
    _, passages = paper(["BN.", "Calibration.", "Calibration preceded calibration."])
    result = select_local_passages(passages, ["BN", "Batch Normalization", "calibration"],
                                   mode="normalized", max_hits=1)
    assert result.hit_indices == (2,)


def test_original_replays_occurrence_tie_document_order_and_neighbors():
    _, passages = paper(["fine-tuning alone.", "Details.", "Fine-tuning and setup.",
                         "Transition.", "SETUP; setup; fine-tuning.", "End."])
    result = select_local_passages(passages, ["fine-tuning", "setup"], mode="original", max_hits=2)
    assert result.ranked_indices == (4, 2, 0)
    assert result.hit_indices == (4, 2)
    assert result.context_indices == (1, 2, 3, 4, 5)
    assert result.character_count == sum(len(passages[i].text) for i in result.context_indices)


def test_heading_supplies_scope_to_later_body_before_the_next_heading():
    _, passages = paper(["Calibration protocol", "Participants completed intake.",
                         "All samples were equilibrated.", "Velocity reached 18 units.",
                         "Other measures", "Velocity reached 70 units in a separate experiment."])
    result = select_local_passages(passages, ["calibration protocol", "velocity"], max_hits=1)
    assert 0 in result.context_indices and 3 in result.context_indices
    assert 5 not in result.context_indices
    # Move the same observation behind another heading: it loses the scope link.
    _, separate = paper(["Calibration protocol", "Participants completed intake.",
                         "Other measures", "Velocity reached 18 units."])
    result = select_local_passages(separate, ["calibration protocol"], max_hits=1)
    assert 3 not in result.context_indices


def test_page_boundary_blocks_inferred_link_even_with_no_intervening_heading():
    _, passages = paper(["Calibration protocol", "Participants completed intake.",
                         "All samples were equilibrated.", "Velocity reached 18 units."],
                        pages=[1, 1, 2, 2])
    result = select_local_passages(passages, ["calibration protocol", "velocity"], max_hits=1)
    assert 3 not in result.context_indices


def test_long_inline_setup_heading_links_its_own_following_body():
    _, passages = paper(["Standard protocol. " + "Samples received identical treatment. " * 7,
                         "All utensils were cleaned.", "A later readout gave an isotope ratio of 3."])
    result = select_local_passages(passages, ["standard protocol", "isotope ratio"], max_hits=1)
    assert result.context_indices == (0, 1, 2)


def test_table_does_not_borrow_a_row_beyond_an_intervening_section_heading():
    _, passages = paper(["Table 2: Data.", "Name | Value", "Base | 4",
                         "Other measurements", "Distractor | 400"])
    result = select_local_passages(passages, ["Table 2"], max_hits=1)
    assert 2 in result.context_indices
    assert 4 not in result.context_indices


@pytest.mark.parametrize("caption_first", [True, False])
def test_named_table_keeps_caption_header_and_target_row_together(caption_first):
    caption = "Table 5: Calibration results."
    table = ["Method | Width | Score", "Alpha | 7 | 0.82", "Beta | 8 | 0.91"]
    block = [caption, *table] if caption_first else [*table, caption]
    source, passages = paper(["Table 5 is discussed below.", "Prior results.", *block,
                              "Other observations.", "Table 50: Other results.", "Wrong | 9 | 1.0"])
    for query in (["Table 5", "Beta"], ["Beta"]):
        result = select_local_passages(passages, query, max_hits=1)
        text = [passages[i].text for i in result.context_indices]
        assert all(part in text for part in [caption, *table])
        assert "Wrong | 9 | 1.0" not in text
        for i in result.context_indices:
            loc = passages[i].location
            assert source[loc.char_start:loc.char_end] == passages[i].text


def test_structural_expansion_fits_whole_groups_after_reserving_base_context(monkeypatch):
    from academic_guardrail.core import local_evidence

    _, passages = paper(["Intro.", "Table 3: Dimensions.", "Item | Size",
                         "A | 7", "B | 8", "End."])
    base = sum(len(p.text) for p in passages[:3])
    monkeypatch.setattr(local_evidence, "MAX_NEW_CHARACTERS", base + len(passages[3].text))
    result = select_local_passages(passages, ["Table 3"], max_hits=1)
    assert result.context_indices == (0, 1, 2)
    assert result.character_count == base
    monkeypatch.setattr(local_evidence, "MAX_NEW_CHARACTERS", base - 1)
    with pytest.raises(ValueError, match="budget"):
        select_local_passages(passages, ["Table 3"], max_hits=1)


def test_legacy_passages_without_positions_and_mixed_file_guard():
    legacy = EvidencePassage(text="A known result.", source_kind="LOCAL_FULLTEXT")
    assert select_local_passages([legacy], ["known"]).context_indices == (0,)
    _, separate = paper(["A known result.", "Wrong file."])
    separate[1].location.file_path = "another.txt"
    with pytest.raises(ValueError, match="one source file"):
        select_local_passages(separate, ["known"])
