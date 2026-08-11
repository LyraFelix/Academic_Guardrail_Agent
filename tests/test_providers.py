"""Tests for academic data providers."""

from unittest.mock import AsyncMock, patch
from academic_guardrail.providers.chinese_academic import ChineseAcademicProvider
from academic_guardrail.providers.claim_eval import ClaimEvaluator


def test_chinese_academic_provider_doi():
    import asyncio
    provider = ChineseAcademicProvider()
    mock_res = {
        "title": "Deep Residual Learning for Image Recognition",
        "doi": "10.1109/cvpr.2016.90",
        "abstract": "Deeper neural networks are more difficult to train.",
        "is_retracted": False
    }
    with patch.object(provider.openalex, "get_by_doi", AsyncMock(return_value=mock_res)):
        res = asyncio.run(provider.verify_citation(title="Deep Residual Learning for Image Recognition", doi="10.1109/CVPR.2016.90"))
    
    assert res["matched"] is True
    assert len(res.get("title", "")) > 0


def test_chinese_core_journal_heuristic_unverified():
    import asyncio
    provider = ChineseAcademicProvider()
    fake_citation = "王某某. 一个完全虚构的论文. 管理世界, 2023."
    with patch.object(provider.openalex, "search_by_title", AsyncMock(return_value=[])), \
         patch.object(provider.crossref, "search_by_title", AsyncMock(return_value=[])):
        res = asyncio.run(provider.verify_citation(title="一个完全虚构的论文", raw_text=fake_citation))

    assert res["matched"] is None
    assert res["confidence"] == 0.40
    assert res["evidence_status"] == "JOURNAL_MATCHED_ARTICLE_UNVERIFIED"
    assert "启发式" in res["source"]


def test_claim_evaluator():
    evaluator = ClaimEvaluator()
    claim = "深度残差网络能够解决深层神经网络的梯度消失与退化问题"
    abstract = "Deep residual networks make it easier to train substantially deeper networks and address degradation problems."
    
    res = evaluator.evaluate_alignment(claim, abstract)
    score, reason, best_sentence = res[0], res[1], res[2]
    assert 0.0 <= score <= 1.0
    assert len(reason) > 0
    assert len(best_sentence) > 0
