"""Unit tests for multilingual (Chinese + English) claim alignment."""

import pytest
from academic_guardrail.providers.claim_eval import ClaimEvaluator, MultilingualFeatureExtractor


class TestChineseClaimAlignment:
    """Tests for Chinese-language claim evaluation."""

    @pytest.fixture
    def evaluator(self):
        return ClaimEvaluator()

    def test_chinese_supports(self, evaluator):
        """Chinese claim that matches Chinese abstract should score high."""
        claim = "人工智能显著提升了企业生产效率"
        abstract = "本研究发现人工智能技术的应用显著提升了企业的生产效率和产出水平"
        score, reason, _ = evaluator.evaluate_alignment(claim, abstract)
        assert score >= 0.20  # Chinese char-ngram overlap should work

    def test_chinese_contradicts(self, evaluator):
        """Chinese claim with polarity inversion should be detected."""
        claim = "人工智能增加了失业率"
        abstract = "研究表明人工智能并未增加失业率，反而降低了结构性失业"
        score, reason, _ = evaluator.evaluate_alignment(claim, abstract)
        # The polarity detection works on Chinese keywords 增加 vs 降低
        # At minimum the score should be moderate
        assert score <= 0.30 or "Polarity" in reason

    def test_chinese_char_ngrams(self):
        """Chinese character n-grams should produce valid overlap."""
        ngrams = MultilingualFeatureExtractor.get_char_ngrams("人工智能提升效率", n=3)
        assert "人工智" in ngrams
        assert "工智能" in ngrams
        assert len(ngrams) > 0

    def test_cross_lingual_en_zh_low(self):
        """English claim vs Chinese abstract should have low similarity."""
        claim = "CRISPR enables genome editing"
        abstract = "基因编辑技术在农业领域具有广泛应用前景"
        score = MultilingualFeatureExtractor.compute_cross_lingual_similarity(claim, abstract)
        assert score < 0.30


class TestMixedLanguageClaims:
    """Tests for mixed English-Chinese scenarios."""

    @pytest.fixture
    def evaluator(self):
        return ClaimEvaluator()

    def test_english_claim_english_abstract(self, evaluator):
        """Standard English-English alignment."""
        score, _, _ = evaluator.evaluate_alignment(
            "Metformin reduces all-cause mortality in diabetic patients.",
            "Metformin therapy was associated with decreased overall mortality rates."
        )
        assert score >= 0.25

    def test_technical_terms_overlap(self):
        """Technical terms like gene names should have high char-ngram overlap."""
        claim = "BRCA1 mutation increases breast cancer risk"
        ref = "BRCA1 germline mutations are associated with elevated breast cancer susceptibility"
        score = MultilingualFeatureExtractor.compute_cross_lingual_similarity(claim, ref)
        assert score > 0.15
