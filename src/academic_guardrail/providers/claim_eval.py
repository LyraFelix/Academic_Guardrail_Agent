"""Claim Evaluator with Dual-Channel Semantic Matching, Lexical Feature Matching, and Polarity Rules."""

import re
import difflib
from typing import Tuple, Dict, Any, Optional
from academic_guardrail.core.semantic_matcher import SemanticMatcher

OPPOSITE_PAIRS = [
    ({"increase", "increases", "increased", "increasing", "promote", "promotes", "promoted", "elevate", "elevates", "elevated", "accelerate", "accelerates", "accelerated", "提升", "增加", "促进", "加速"},
     {"inhibit", "inhibits", "inhibited", "decrease", "decreases", "decreased", "reduce", "reduces", "reduced", "prevent", "prevents", "slow down", "slows down", "slowed down", "did not lower", "did not reduce", "not increase", "no effect", "抑制", "降低", "减少", "阻碍"}),

    ({"reduce", "reduces", "reduced", "reducing", "lower", "lowers", "lowered", "prevent", "prevents", "inhibit", "inhibited", "降低", "减少", "抑制"},
     {"did not lower", "did not reduce", "failed to lower", "failed to reduce", "elevate", "elevates", "elevated", "increase", "increases", "increased", "accelerate", "accelerates", "accelerated", "未降低", "未减少", "提升", "增加"})
]

SYNONYM_MAP = {
    "enable": {"allow", "permit", "facilitate", "enable", "enables", "enabled"},
    "allow": {"enable", "permit", "facilitate", "allow", "allows", "allowed"},
    "reduce": {"decrease", "lower", "diminish", "curtail", "reduce", "reduces", "reduced"},
    "decrease": {"reduce", "lower", "diminish", "decrease", "decreases", "decreased"},
    "promote": {"increase", "elevate", "enhance", "stimulate", "promote", "promotes", "promoted"},
    "increase": {"promote", "elevate", "enhance", "stimulate", "increase", "increases", "increased"},
}


class MultilingualFeatureExtractor:
    """Extracts surface-level lexical features (Stems, Char N-Grams, and Sequence Ratios)."""

    @staticmethod
    def stem_word(word: str) -> str:
        w = word.lower().strip()
        for suffix in ['ing', 'tion', 'ness', 'ment', 'able', 'ed', 'es', 's']:
            if len(w) > 4 and w.endswith(suffix):
                return w[:-len(suffix)]
        return w

    @staticmethod
    def get_stems(text: str) -> set:
        words = re.findall(r'\b\w{3,}\b', text.lower())
        stems = set()
        for w in words:
            stems.add(MultilingualFeatureExtractor.stem_word(w))
            if w in SYNONYM_MAP:
                stems.update([MultilingualFeatureExtractor.stem_word(syn) for syn in SYNONYM_MAP[w]])
        return stems

    @staticmethod
    def get_char_ngrams(text: str, n: int = 3) -> set:
        clean = re.sub(r'[^\w\s]', '', text.lower()).strip()
        if not clean:
            return set()
        return set(clean[i:i+n] for i in range(len(clean) - n + 1))

    @staticmethod
    def compute_lexical_similarity(claim: str, sentence: str) -> float:
        """Pure surface lexical matching: 0.50 Stem Overlap + 0.30 Char N-Gram + 0.20 Sequence Matcher."""
        if not claim or not sentence:
            return 0.0

        c_stems = MultilingualFeatureExtractor.get_stems(claim)
        s_stems = MultilingualFeatureExtractor.get_stems(sentence)
        c_ngrams = MultilingualFeatureExtractor.get_char_ngrams(claim, n=3)
        s_ngrams = MultilingualFeatureExtractor.get_char_ngrams(sentence, n=3)

        stem_overlap = (len(c_stems.intersection(s_stems)) / float(max(len(c_stems), 1))) if c_stems and s_stems else 0.0
        ngram_jaccard = (len(c_ngrams.intersection(s_ngrams)) / float(max(len(c_ngrams.union(s_ngrams)), 1))) if c_ngrams and s_ngrams else 0.0
        seq_sim = difflib.SequenceMatcher(None, claim.lower(), sentence.lower()).ratio()

        lexical_score = 0.50 * stem_overlap + 0.30 * ngram_jaccard + 0.20 * seq_sim
        return round(lexical_score, 2)

    @classmethod
    def compute_cross_lingual_similarity(cls, claim: str, sentence: str) -> float:
        return cls.compute_lexical_similarity(claim, sentence)


class NegationScopeDetector:
    """Detects negation scope and polarity in claims and abstracts."""

    NEGATION_MARKERS = {
        "not", "no", "never", "cannot", "can't", "fail", "failed", "fails", "failing",
        "without", "neither", "nor", "lack", "lacks", "lacking", "lacked",
        "未", "不", "没有", "未曾", "无法", "未能", "毫无"
    }

    POS_VERBS = {
        "increase", "increases", "increased", "increasing",
        "promote", "promotes", "promoted", "promoting",
        "elevate", "elevates", "elevated", "elevating",
        "accelerate", "accelerates", "accelerated", "accelerating",
        "提升", "提升了", "增加", "增加了", "促进", "促进了", "加速", "加速了"
    }

    NEG_VERBS = {
        "reduce", "reduces", "reduced", "reducing",
        "lower", "lowers", "lowered", "lowering",
        "inhibit", "inhibits", "inhibited", "inhibiting",
        "decrease", "decreases", "decreased", "decreasing",
        "prevent", "prevents", "prevented", "preventing",
        "slow down", "slows down", "slowed down",
        "抑制", "抑制了", "降低", "降低了", "减少", "减少了", "阻碍", "阻碍了"
    }

    @classmethod
    def get_text_polarity_profile(cls, text: str) -> Dict[str, bool]:
        t = text.lower()
        has_pos_polarity = False
        has_neg_polarity = False

        cn_neg_markers = ["未", "不", "没有", "未曾", "无法", "未能", "毫无"]
        cn_pos_verbs = ["提升", "增加", "促进", "加速"]
        cn_neg_verbs = ["降低", "减少", "抑制", "阻碍"]

        for v in cn_pos_verbs:
            if v in t:
                v_idx = t.find(v)
                prefix = t[max(0, v_idx - 10):v_idx]
                if any(m in prefix for m in cn_neg_markers):
                    has_neg_polarity = True
                else:
                    has_pos_polarity = True

        for v in cn_neg_verbs:
            if v in t:
                v_idx = t.find(v)
                prefix = t[max(0, v_idx - 10):v_idx]
                if any(m in prefix for m in cn_neg_markers):
                    has_pos_polarity = True
                else:
                    has_neg_polarity = True

        words = re.findall(r'\b[a-zA-Z]+\b', t)
        for idx, word in enumerate(words):
            if word in cls.POS_VERBS:
                lookback = words[max(0, idx - 4):idx]
                if any(m in lookback for m in cls.NEGATION_MARKERS):
                    has_neg_polarity = True
                else:
                    has_pos_polarity = True
            elif word in cls.NEG_VERBS:
                lookback = words[max(0, idx - 4):idx]
                if any(m in lookback for m in cls.NEGATION_MARKERS):
                    has_pos_polarity = True
                else:
                    has_neg_polarity = True

        return {"has_pos": has_pos_polarity, "has_neg": has_neg_polarity}


class ClaimEvaluator:
    """Dual-Channel Alignment Evaluator: 0.55 Semantic Embedding + 0.35 Lexical Matching + 0.10 Polarity Alignment."""

    def __init__(self):
        self.semantic_matcher = SemanticMatcher()

    def find_best_matching_sentence(self, claim: str, abstract: str) -> Tuple[str, float]:
        if not claim or not abstract:
            return "", 0.0

        sentences = [s.strip() for s in re.split(r'[\.\?\!\;\n]\s*', abstract) if len(s.strip()) > 10]
        if not sentences:
            return abstract[:150], 0.40

        best_sent = sentences[0]
        best_score = 0.0

        for sent in sentences:
            semantic_score = self.semantic_matcher.compute_similarity(claim, sent)
            lexical_score = MultilingualFeatureExtractor.compute_lexical_similarity(claim, sent)
            fusion_score = 0.55 * semantic_score + 0.45 * lexical_score
            if fusion_score > best_score:
                best_score = fusion_score
                best_sent = sent

        return best_sent, round(best_score, 2)

    def evaluate_alignment(self, claim: str, abstract: str) -> Tuple[float, str, str]:
        """Returns (final_score, reason, best_matching_abstract_sentence).
        
        Final Score Formula:
            0.55 * semantic_score + 0.35 * lexical_score + 0.10 * polarity_score
        """
        if not claim or not abstract:
            return 0.0, "Missing claim or abstract", ""

        c_text = claim.lower().strip()
        a_text = abstract.lower().strip()

        best_sentence, sent_score = self.find_best_matching_sentence(claim, abstract)

        # 1. Scope-Aware Negation & Polarity Contradiction Detection
        c_profile = NegationScopeDetector.get_text_polarity_profile(claim)
        a_profile = NegationScopeDetector.get_text_polarity_profile(abstract)

        if (c_profile["has_pos"] and a_profile["has_neg"]) or (c_profile["has_neg"] and a_profile["has_pos"]):
            return 0.15, "Polarity mismatch: Scope-aware negation indicates claim directly contradicts abstract conclusion", best_sentence

        for pos_set, neg_set in OPPOSITE_PAIRS:
            c_has_neg = any(w in c_text for w in neg_set)
            c_has_pos = any(w in c_text for w in pos_set) and not c_has_neg

            a_has_neg = any(re.search(r'\b' + re.escape(w) + r'\b', a_text) for w in neg_set)
            a_has_pos = any(re.search(r'\b' + re.escape(w) + r'\b', a_text) for w in pos_set) and not a_has_neg

            if (c_has_pos and a_has_neg) or (c_has_neg and a_has_pos):
                return 0.15, "Polarity mismatch: Claim directly contradicts abstract conclusion", best_sentence

        # 2. Dual-Channel Score Fusion
        semantic_score = self.semantic_matcher.compute_similarity(claim, abstract)
        lexical_score = MultilingualFeatureExtractor.compute_lexical_similarity(claim, abstract)

        has_overlap = (semantic_score >= 0.20) or (lexical_score >= 0.20)
        polarity_score = 1.0 if has_overlap else 0.0

        fusion_score = (
            0.55 * semantic_score +
            0.35 * lexical_score +
            0.10 * polarity_score
        )
        final_score = round(max(fusion_score, sent_score), 2)

        if final_score >= 0.25:
            reason = "正文断言与文献摘要核心观点高度吻合"
        elif final_score >= 0.15:
            reason = "断言与摘要部分重合，建议人工核对"
        else:
            reason = "正文断言与摘要语义匹配度较低"

        return final_score, reason, best_sentence
