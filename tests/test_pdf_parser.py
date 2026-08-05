"""Unit tests for DocumentParser: PDF, DOCX, text, and arXiv URL parsing."""

import os
import tempfile
import pytest
from academic_guardrail.core.parser import DocumentParser


class TestDocumentParser:
    """Tests for the multi-format document parser."""

    @pytest.fixture
    def parser(self):
        return DocumentParser()

    def test_parse_text_file(self, parser, tmp_path):
        """Parse a plain text file with GB/T 7714 references."""
        content = (
            "人工智能正在改变社会生产方式[1]。\n"
            "\n"
            "[1] 姚加权, 冯展斌. 人工智能如何提升企业生产效率[J]. 经济研究, 2023.\n"
        )
        txt_file = tmp_path / "test.txt"
        txt_file.write_text(content, encoding="utf-8")
        pairs = parser.parse_document(str(txt_file))
        assert len(pairs) >= 1
        citation, claim = pairs[0]
        assert citation.id == "cit_1"
        assert "人工智能" in citation.raw_text

    def test_parse_nonexistent_file(self, parser):
        """Should raise FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError):
            parser.parse_document("/nonexistent/path/file.docx")

    def test_parse_empty_text(self, parser, tmp_path):
        """Empty file should return empty list."""
        txt_file = tmp_path / "empty.txt"
        txt_file.write_text("", encoding="utf-8")
        pairs = parser.parse_document(str(txt_file))
        assert pairs == []

    def test_parse_arxiv_url(self, parser):
        """arXiv URL should be parsed into citation with DOI."""
        pairs = parser.parse_document("https://arxiv.org/abs/1706.03762")
        assert len(pairs) == 1
        citation, claim = pairs[0]
        assert "1706.03762" in citation.doi
        assert citation.id == "cit_arxiv_1"

    def test_parse_arxiv_id(self, parser):
        """Bare arXiv ID should also be parsed."""
        pairs = parser.parse_document("2301.07041")
        assert len(pairs) == 1
        assert "2301.07041" in pairs[0][0].doi

    def test_parse_markdown_file(self, parser, tmp_path):
        """Parse a markdown file with inline citations."""
        content = (
            "# Research Paper\n\n"
            "Studies show significant improvement [1].\n\n"
            "## References\n"
            "[1] Smith J, Doe A. Deep Learning for NLP[J]. Nature, 2023.\n"
        )
        md_file = tmp_path / "test.md"
        md_file.write_text(content, encoding="utf-8")
        pairs = parser.parse_document(str(md_file))
        assert len(pairs) >= 1

    def test_unknown_extension_fallback(self, parser, tmp_path):
        """Unknown extensions should fallback to text parsing."""
        content = "[1] Author. Some Title[J]. Journal, 2023.\n"
        f = tmp_path / "test.xyz"
        f.write_text(content, encoding="utf-8")
        pairs = parser.parse_document(str(f))
        assert len(pairs) >= 1
