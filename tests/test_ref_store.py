"""Unit tests for content-based LocalRefStore indexing with arbitrary filenames."""

import os
import tempfile
import pytest
from academic_guardrail.core.ref_store import LocalRefStore


@pytest.mark.parametrize("continuation", [
    "results on three downstream benchmarks.",
    "methods that use only the training split.",
    "introduction of image transformers.",
    "discussion of their practical implications.",
])
@pytest.mark.parametrize("heading", ["1. Introduction", "INTRODUCTION"])
def test_abstract_line_wrap_is_not_a_section_heading(tmp_path, continuation, heading):
    """PDF line wrapping must not turn a sentence fragment into a heading."""
    abstract = "We report new\n" + continuation + "\nThese findings motivate further study."
    text = "A test paper\n\nAbstract\n" + abstract + "\n" + heading + "\nBody text."
    path = tmp_path / "paper.txt"
    path.write_text(text, encoding="utf-8")

    record = LocalRefStore(str(tmp_path)).records[0]

    assert record.abstract == abstract
    assert text[record.abstract_location.char_start:record.abstract_location.char_end] == abstract


def test_local_ref_store_arbitrary_filename_matching():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a PDF/TXT file with completely unrelated filename
        unrelated_filename = "2023_v2_draft_final.txt"
        file_path = os.path.join(tmpdir, unrelated_filename)

        content = (
            "Deep Reinforcement Learning for Autonomous Driving Systems\n"
            "John Doe, Jane Smith\n"
            "2023\n\n"
            "Abstract: This paper presents a novel deep reinforcement learning framework "
            "for end-to-end autonomous driving in complex urban environments.\n\n"
            "1. Introduction\n"
            "Autonomous driving requires robust control..."
        )

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Index directory
        ref_store = LocalRefStore(tmpdir)
        assert len(ref_store.records) == 1
        record = ref_store.records[0]
        assert record.title == "Deep Reinforcement Learning for Autonomous Driving Systems"
        assert "autonomous driving" in record.abstract.lower()

        # Query using paper title (not filename)
        result = ref_store.find_abstract_for_citation(
            title="Deep Reinforcement Learning for Autonomous Driving Systems",
            raw_text="[1] John Doe, Jane Smith. Deep Reinforcement Learning for Autonomous Driving Systems[J]. 2023."
        )

        assert result is not None
        matched_text, source_fn, conf = result
        assert source_fn == "2023_v2_draft_final.txt"
        assert "autonomous driving" in matched_text.lower()
        assert conf > 0.0
