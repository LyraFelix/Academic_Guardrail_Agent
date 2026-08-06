"""Unit tests for DOI resolution and Retraction Checkers."""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from academic_guardrail.providers.chinese_academic import ChineseAcademicProvider


def test_retracted_doi_detection():
    """Provider should correctly pass through is_retracted=True from OpenAlex/Crossref API."""
    provider = ChineseAcademicProvider()
    mock_openalex = AsyncMock(return_value={
        "title": "Retracted: Some Paper",
        "doi": "10.1016/j.cell.2006.02.001",
        "abstract": "",
        "is_retracted": True
    })
    mock_crossref = AsyncMock(return_value=None)
    with patch.object(provider.openalex, "get_by_doi", mock_openalex), \
         patch.object(provider.crossref, "get_by_doi", mock_crossref):
        res = asyncio.run(provider.verify_citation(title="", doi="10.1016/j.cell.2006.02.001"))
    assert res["matched"] is True
    assert res["is_retracted"] is True


def test_valid_doi_resolution():
    """Title-based resolution via Crossref/OpenAlex."""
    provider = ChineseAcademicProvider()
    mock_cand = [{
        "title": "Attention Is All You Need",
        "doi": "10.48550/arxiv.1706.03762",
        "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.",
        "is_retracted": False
    }]
    with patch.object(provider.openalex, "search_by_title", AsyncMock(return_value=mock_cand)):
        res = asyncio.run(provider.verify_citation(
            title="Attention Is All You Need", doi=None
        ))
    assert res["matched"] is True
    assert res["is_retracted"] is False
