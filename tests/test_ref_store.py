"""Unit tests for content-based LocalRefStore indexing with arbitrary filenames."""

import os
import tempfile
import pytest
from academic_guardrail.core.ref_store import LocalRefStore


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
