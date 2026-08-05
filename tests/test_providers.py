"""Tests for academic data providers."""

import pytest
from academic_guardrail.providers.chinese_academic import ChineseAcademicProvider
from academic_guardrail.providers.claim_eval import ClaimEvaluator


def test_chinese_academic_provider_doi():
    import asyncio
    provider = ChineseAcademicProvider()
    # Test with a known stable title and DOI
    res = asyncio.run(provider.verify_citation(title="Deep Residual Learning for Image Recognition", doi="10.1109/CVPR.2016.90"))
    
    assert res["matched"] is True
    assert len(res.get("title", "")) > 0



def test_claim_evaluator():
    evaluator = ClaimEvaluator()
    claim = "深度残差网络能够解决深层神经网络的梯度消失与退化问题"
    abstract = "Deep residual networks make it easier to train substantially deeper networks and address degradation problems."
    
    score, reason, best_sentence = evaluator.evaluate_alignment(claim, abstract)
    assert 0.0 <= score <= 1.0
    assert len(reason) > 0
    assert len(best_sentence) > 0
