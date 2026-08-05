"""Unit tests for DOI resolution and Retraction Checkers."""

import pytest
import asyncio
from academic_guardrail.providers.chinese_academic import ChineseAcademicProvider


def test_retracted_doi_detection():
    """Retraction Watch offline index should flag known retracted papers."""
    provider = ChineseAcademicProvider()
    res = asyncio.run(provider.verify_citation(title="", doi="10.1016/j.cell.2006.02.001"))
    assert res["matched"] is True
    assert res["is_retracted"] is True


def test_valid_doi_resolution():
    """Title-based resolution via Crossref (network-dependent)."""
    provider = ChineseAcademicProvider()
    res = asyncio.run(provider.verify_citation(
        title="Attention Is All You Need", doi=None
    ))
    assert res["matched"] is True
    assert res["is_retracted"] is False
