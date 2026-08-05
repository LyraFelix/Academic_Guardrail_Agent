# -*- coding: utf-8 -*-
"""Unit tests for Multilingual Feature Extractor & Sentence-Level Locator."""

import pytest
from academic_guardrail.providers.claim_eval import (
    MultilingualFeatureExtractor,
    ClaimEvaluator
)


def test_multilingual_feature_extractor():
    extractor = MultilingualFeatureExtractor()

    # 1. Test Stemming & Synonym expansion
    stems = extractor.get_stems("The algorithm enables significant performance increase")
    assert "increas" in stems or "increase" in stems or "promot" in stems
    assert "allow" in stems or "facilit" in stems or "enabl" in stems

    # 2. Test Cross-Lingual similarity calculation
    claim = "Deep learning techniques significantly improve efficiency"
    sentence = "Deep learning techniques significantly improve computational efficiency and scalability."
    sim = extractor.compute_cross_lingual_similarity(claim, sentence)
    assert sim >= 0.20


def test_sentence_locator_and_antonym_contradiction():
    evaluator = ClaimEvaluator()

    # 1. Test Sentence-Level Locator
    claim = "Deep residual networks make training deeper models easier."
    abstract = (
        "Neural networks are hard to train. "
        "Deep residual networks make it easier to train substantially deeper networks. "
        "We evaluate our approach on ImageNet."
    )
    best_sent, score = evaluator.find_best_matching_sentence(claim, abstract)
    assert "Deep residual networks make it easier" in best_sent
    assert score >= 0.25

    # 2. Test Polarity Antonym Contradiction Detection
    bad_claim = "The proposed method failed to lower structural unemployment"
    good_abstract = "The proposed algorithm significantly reduced structural unemployment across all sectors."
    score, reason, best_s = evaluator.evaluate_alignment(bad_claim, good_abstract)

    assert score <= 0.15
    assert "Polarity" in reason or "不匹配" in reason
