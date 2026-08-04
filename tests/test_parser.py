"""Tests for document parser."""

import os
import pytest
from academic_guardrail.core.parser import DocumentParser


def test_parse_gbt7714_text(tmp_path):
    sample_text = """
    近年来，深度学习在自然语言处理领域取得了显著进展 [1]。
    
    参考文献：
    [1] 张三, 李四. 某种深度学习模型算法研究[J]. 计算机学报, 2022.
    [2] 10.1016/j.cell.2020.01.001
    """
    file_path = tmp_path / "sample.md"
    file_path.write_text(sample_text, encoding="utf-8")

    parser = DocumentParser()
    pairs = parser.parse_document(str(file_path))

    assert len(pairs) >= 1
    cit, claim = pairs[0]
    assert "张三" in cit.authors or "10.1016" in cit.raw_text or "深度学习" in cit.title
    assert claim.citation_id == cit.id
