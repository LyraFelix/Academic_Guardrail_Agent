"""Regression checks for the evidence-coverage metric, independent of private archives."""

from hashlib import sha256
from importlib.util import find_spec
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from academic_guardrail.core.models import EvidencePassage, SourceLocation
from benchmarks.replay_manuscript_retrieval import Archive, merge_evidence, mode_result, run, runtime_hashes, span_covered


def passage(text, start=0):
    return EvidencePassage(text=text, source_kind="LOCAL_FULLTEXT", location=SourceLocation(
        file_path="fixed.txt", char_start=start, char_end=start + len(text), line=1))


def test_coverage_requires_all_nonspace_source_characters_and_original_offsets():
    source = "Batch 4.\nBatch 4.\nDefault."
    units = merge_evidence([], [passage("Batch 4."), passage("Default.", 18)])
    assert span_covered(source, units, {"canonical_start": 0, "canonical_end": 9})
    assert not span_covered(source, units, {"canonical_start": 9, "canonical_end": 17})
    assert not span_covered(source, units, {"canonical_start": 0, "canonical_end": len(source)})
    assert merge_evidence(units, [passage("Batch 4.")]) == units


def test_carried_case_keeps_parent_and_requires_complete_alternative_group():
    paper = SimpleNamespace(record=SimpleNamespace(fulltext="Table. Same. Other.", passages=[]))
    parent = merge_evidence([], [passage("Same.", 7)])
    spans = {"anchor": {"canonical_start": 0, "canonical_end": 6},
             "local:e2": {"canonical_start": 7, "canonical_end": 12},
             "scope": {"canonical_start": 13, "canonical_end": 19}}
    def check(groups):
        mode, actual = mode_result(parent, paper, [], "original", 3, 18000, spans, groups, [])
        assert actual == parent
        assert mode["context_characters"] == 0
        assert mode["hit_indices"] == mode["context_indices"] == []
        return mode
    local = check([["anchor"], ["local:e2"]])
    assert local["complete_witness_group"] and local["anchor_or_audited_old_alternative"]
    assert check([["local:e2", "scope"]])["complete_witness_group"] is False
    insufficient = check([])
    assert insufficient["complete_witness_group"] is None  # A true NEI has no positive decision witness.
    assert insufficient["anchor_or_audited_old_alternative"] is None


def test_tampered_delivery_hash_and_archive_output_fail_closed(tmp_path):
    (tmp_path / "final_delivery_manifest_02.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Archive hash differs"):
        Archive(tmp_path, "0" * 64)
    with pytest.raises(ValueError, match="outside the frozen archive"):
        run(tmp_path, tmp_path / "new-output")
    assert not (tmp_path / "new-output").exists()


def test_manifest_hashes_word_layout_source_without_loading_docx_reader(monkeypatch):
    name = "academic_guardrail.core.docx_numbering"
    monkeypatch.delitem(sys.modules, name, raising=False)
    path = Path(find_spec(name).origin)
    assert runtime_hashes()["docx_numbering"] == sha256(path.read_bytes()).hexdigest()
    assert name not in sys.modules
