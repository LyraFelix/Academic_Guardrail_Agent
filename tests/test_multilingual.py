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
        res = evaluator.evaluate_alignment(claim, abstract)
        score, reason, _, alignment_state = res[0], res[1], res[2], res[3]
        assert score >= 0.20
        assert alignment_state in ("SUPPORTED", "PARTIAL")

    def test_chinese_contradicts(self, evaluator):
        """Chinese claim with polarity inversion should be detected."""
        claim = "人工智能增加了失业率"
        abstract = "研究表明人工智能并未增加失业率，反而降低了结构性失业"
        res = evaluator.evaluate_alignment(claim, abstract)
        score, reason, _, alignment_state = res[0], res[1], res[2], res[3]
        assert alignment_state == "CONTRADICTED"
        assert score <= 0.30 or "Polarity" in reason or "极性" in reason

    def test_chinese_sentence_splitting(self, evaluator):
        """Chinese full-width punctuation (。！？；) should properly split text into sentence units."""
        zh_text = "本文研究人工智能。结果表明生产率显著提高！进一步发现其重塑了劳动力市场结构；本研究为政策制定提供了依据？"
        sents = evaluator.split_sentences(zh_text)
        assert len(sents) == 4
        assert "本文研究人工智能" in sents[0]
        assert "结果表明生产率显著提高" in sents[1]
        assert "进一步发现其重塑了劳动力市场结构" in sents[2]
        assert "本研究为政策制定提供了依据" in sents[3]

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
        res = evaluator.evaluate_alignment(
            "Metformin reduces all-cause mortality in diabetic patients.",
            "Metformin therapy was associated with decreased overall mortality rates."
        )
        score, alignment_state = res[0], res[3]
        assert score >= 0.25
        assert alignment_state in ("SUPPORTED", "PARTIAL")

    def test_cross_lingual_same_semantics_high(self, evaluator):
        """Cross-lingual regression case: Chinese claim vs semantically identical English abstract."""
        claim_1 = "自动化技术改变劳动力市场结构"
        abstract_1 = "Automation technologies reshape labor demand and employment patterns."

        res_1 = evaluator.evaluate_alignment(claim_1, abstract_1)
        score_1, alignment_state_1 = res_1[0], res_1[3]

        assert score_1 >= 0.20
        assert alignment_state_1 in ("SUPPORTED", "PARTIAL")

        claim_2 = "人工智能技术的发展可能改变劳动力市场结构"
        abstract_2 = "Technological progress in artificial intelligence has significant implications for labor market transformation."

        res_2 = evaluator.evaluate_alignment(claim_2, abstract_2)
        score_2, alignment_state_2 = res_2[0], res_2[3]

        assert score_2 >= 0.20
        assert alignment_state_2 in ("SUPPORTED", "PARTIAL")

    def test_technical_terms_overlap(self):
        """Technical terms like gene names should have high char-ngram overlap."""
        claim = "BRCA1 mutation increases breast cancer risk"
        ref = "BRCA1 germline mutations are associated with elevated breast cancer susceptibility"
        score = MultilingualFeatureExtractor.compute_cross_lingual_similarity(claim, ref)
        assert score > 0.15
