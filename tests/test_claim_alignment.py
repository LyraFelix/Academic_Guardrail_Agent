"""Unit tests for claim alignment and polarity contradiction detection."""

import pytest
from academic_guardrail.providers.claim_eval import ClaimEvaluator, MultilingualFeatureExtractor


class TestMultilingualFeatureExtractor:
    """Tests for the cross-lingual feature extraction pipeline."""

    def test_stem_word_english(self):
        assert MultilingualFeatureExtractor.stem_word("increasing") == "increas"
        assert MultilingualFeatureExtractor.stem_word("promoted") == "promot"
        assert MultilingualFeatureExtractor.stem_word("reduction") == "reduc"

    def test_stem_word_short_preserved(self):
        """Words <= 4 chars should not be stemmed."""
        assert MultilingualFeatureExtractor.stem_word("cat") == "cat"
        assert MultilingualFeatureExtractor.stem_word("is") == "is"

    def test_char_ngrams(self):
        ngrams = MultilingualFeatureExtractor.get_char_ngrams("hello", n=3)
        assert "hel" in ngrams
        assert "ell" in ngrams
        assert "llo" in ngrams
        assert len(ngrams) == 3

    def test_char_ngrams_empty(self):
        assert MultilingualFeatureExtractor.get_char_ngrams("", n=3) == set()

    def test_identical_text_high_similarity(self):
        text = "CRISPR-Cas9 enables precise genome editing"
        score = MultilingualFeatureExtractor.compute_cross_lingual_similarity(text, text)
        assert score >= 0.80

    def test_unrelated_text_low_similarity(self):
        claim = "Quantum computing improves NLP"
        ref = "Deep learning models require large GPU memory"
        score = MultilingualFeatureExtractor.compute_cross_lingual_similarity(claim, ref)
        assert score < 0.25

    def test_synonym_expansion_boosts_score(self):
        """Synonym map should boost alignment for semantically equivalent terms."""
        claim = "Metformin reduces mortality"
        ref = "Metformin decreases overall death rate"
        score = MultilingualFeatureExtractor.compute_cross_lingual_similarity(claim, ref)
        assert score > 0.15  # synonym 'reduce' ↔ 'decrease' should help

    def test_empty_inputs(self):
        assert MultilingualFeatureExtractor.compute_cross_lingual_similarity("", "text") == 0.0
        assert MultilingualFeatureExtractor.compute_cross_lingual_similarity("text", "") == 0.0


class TestClaimEvaluator:
    """Tests for evaluate_alignment and polarity contradiction detection."""

    @pytest.fixture
    def evaluator(self):
        return ClaimEvaluator()

    # ── SUPPORTS cases ──
    def test_supports_identical(self, evaluator):
        score, reason, _ = evaluator.evaluate_alignment(
            "Visual hallucinations occur in 60% of Parkinson's patients.",
            "Visual hallucinations occur in up to 60% of patients with Parkinson's disease."
        )
        assert score >= 0.25
        assert "Polarity mismatch" not in reason

    def test_supports_paraphrase(self, evaluator):
        score, reason, _ = evaluator.evaluate_alignment(
            "STING activation stimulates type I interferon production.",
            "Activation of the STING pathway induces robust type I interferon responses."
        )
        assert score >= 0.25

    # ── CONTRADICTS cases ──
    def test_contradicts_increase_vs_inhibit(self, evaluator):
        score, reason, _ = evaluator.evaluate_alignment(
            "AMPK activation directly increases cancer cell proliferation.",
            "AMPK activation inhibits cell proliferation in multiple cancer cell lines."
        )
        assert "Polarity mismatch" in reason
        assert score <= 0.20

    def test_negation_scope_does_not_significantly_increase(self, evaluator):
        """Adverbial inserted negation 'does not significantly increase' should be recognized as negative polarity."""
        score, reason, _ = evaluator.evaluate_alignment(
            "The proposed method significantly increases classification accuracy.",
            "Experimental results demonstrate that the method does not significantly increase accuracy."
        )
        assert "Polarity mismatch" in reason

    def test_negation_scope_failed_to_markedly_lower(self, evaluator):
        """Scope-aware negation 'failed to markedly lower' should invert lower (negative) into positive retention."""
        score, reason, _ = evaluator.evaluate_alignment(
            "Treatment significantly lowers serum cholesterol levels.",
            "Clinical trials showed that the treatment failed to markedly lower serum cholesterol."
        )
        assert "Polarity mismatch" in reason

    def test_negation_scope_chinese_adverb(self, evaluator):
        """Chinese negation scope '未显著提升' should be recognized as negative polarity."""
        score, reason, _ = evaluator.evaluate_alignment(
            "该方案显著提升了企业生产效率",
            "实证分析表明，该方案未显著提升企业生产效率"
        )
        assert "Polarity mismatch" in reason

    def test_contradicts_reduce_vs_did_not_lower(self, evaluator):
        score, reason, _ = evaluator.evaluate_alignment(
            "Vitamin D supplementation reduces total cardiovascular events.",
            "Randomized trial showed Vitamin D did not lower cardiovascular risk."
        )
        assert "Polarity mismatch" in reason

    def test_contradicts_elevate_vs_not_increase(self, evaluator):
        score, reason, _ = evaluator.evaluate_alignment(
            "Statins significantly elevate blood pressure in hypertensive patients.",
            "Statins do not increase blood pressure and slightly attenuate hypertension."
        )
        assert "Polarity mismatch" in reason

    def test_contradicts_accelerate_vs_slow_down(self, evaluator):
        score, reason, _ = evaluator.evaluate_alignment(
            "Calorie restriction accelerates cellular aging process.",
            "Caloric restriction slows down biological aging and extends lifespan."
        )
        assert "Polarity mismatch" in reason

    # ── NEUTRAL cases ──
    def test_neutral_unrelated_topics(self, evaluator):
        score, reason, _ = evaluator.evaluate_alignment(
            "Quantum computing improves natural language processing.",
            "Deep learning models require large GPU memory during training."
        )
        assert score < 0.25
        assert "Polarity mismatch" not in reason

    # ── Edge cases ──
    def test_empty_claim(self, evaluator):
        score, reason, _ = evaluator.evaluate_alignment("", "Some abstract text here.")
        assert score == 0.0

    def test_empty_abstract(self, evaluator):
        score, reason, _ = evaluator.evaluate_alignment("Some claim.", "")
        assert score == 0.0

    # ── Sentence-level matching ──
    def test_find_best_matching_sentence(self, evaluator):
        abstract = (
            "Background: This study investigates AMPK signaling. "
            "AMPK activation inhibits cell proliferation in multiple cancer cell lines. "
            "Conclusion: AMPK is a tumor suppressor."
        )
        best_sent, score = evaluator.find_best_matching_sentence(
            "AMPK activation increases cancer cell proliferation", abstract
        )
        # Should match the sentence about AMPK and proliferation
        assert "proliferation" in best_sent.lower()
        assert score > 0.0

    def test_find_best_matching_sentence_empty(self, evaluator):
        sent, score = evaluator.find_best_matching_sentence("claim", "")
        assert sent == ""
        assert score == 0.0
