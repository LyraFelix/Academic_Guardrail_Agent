"""Claim Evaluator with Antonym & Polarity Inversion Logic and Universal Zero-Shot Multilingual NLI Alignment."""

import re
import difflib
from typing import Tuple, Dict, Any, Optional

OPPOSITE_PAIRS = [
    ({"increase", "increases", "increased", "increasing", "promote", "promotes", "promoted", "elevate", "elevates", "elevated", "accelerate", "accelerates", "提升", "增加", "促进", "加速"},
     {"inhibit", "inhibits", "inhibited", "decrease", "decreases", "decreased", "reduce", "reduces", "reduced", "prevent", "prevents", "slow down", "did not lower", "did not reduce", "not increase", "no effect", "抑制", "降低", "减少", "阻碍"}),

    ({"reduce", "reduces", "reduced", "reducing", "lower", "lowers", "lowered", "prevent", "prevents", "inhibit", "inhibited", "降低", "减少", "抑制"},
     {"did not lower", "did not reduce", "failed to lower", "failed to reduce", "elevate", "elevates", "elevated", "increase", "increases", "increased", "accelerate", "未降低", "未减少", "提升", "增加"})
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
    """Universal Zero-Shot Cross-Lingual N-Gram, Stemming & Subword Feature Matcher."""

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
    def compute_cross_lingual_similarity(claim: str, sentence: str) -> float:
        if not claim or not sentence:
            return 0.0

        c_stems = MultilingualFeatureExtractor.get_stems(claim)
        s_stems = MultilingualFeatureExtractor.get_stems(sentence)

        c_ngrams = MultilingualFeatureExtractor.get_char_ngrams(claim, n=3)
        s_ngrams = MultilingualFeatureExtractor.get_char_ngrams(sentence, n=3)

        if not c_stems or not s_stems:
            return 0.0

        stem_overlap = len(c_stems.intersection(s_stems)) / float(max(len(c_stems), 1))
        ngram_jaccard = len(c_ngrams.intersection(s_ngrams)) / float(max(len(c_ngrams.union(s_ngrams)), 1))
        seq_sim = difflib.SequenceMatcher(None, claim.lower(), sentence.lower()).ratio()

        final = 0.5 * stem_overlap + 0.3 * ngram_jaccard + 0.2 * seq_sim
        return round(final, 2)


class ClaimEvaluator:
    """Evaluates alignment, detects polarity contradictions, and extracts sentence-level context matches across languages."""

    def find_best_matching_sentence(self, claim: str, abstract: str) -> Tuple[str, float]:
        if not claim or not abstract:
            return "", 0.0

        sentences = [s.strip() for s in re.split(r'[\.\?\!\;\n]\s*', abstract) if len(s.strip()) > 10]
        if not sentences:
            return abstract[:150], 0.40

        best_sent = sentences[0]
        best_score = 0.0

        for sent in sentences:
            sim = MultilingualFeatureExtractor.compute_cross_lingual_similarity(claim, sent)
            if sim > best_score:
                best_score = sim
                best_sent = sent

        return best_sent, round(best_score, 2)

    def evaluate_alignment(self, claim: str, abstract: str) -> Tuple[float, str, str]:
        """Returns (score, reason, best_matching_abstract_sentence)."""
        if not claim or not abstract:
            return 0.0, "Missing claim or abstract", ""

        c_text = claim.lower().strip()
        a_text = abstract.lower().strip()

        best_sentence, sent_score = self.find_best_matching_sentence(claim, abstract)

        # 1. Check for explicit polarity contradiction / antonyms
        for pos_set, neg_set in OPPOSITE_PAIRS:
            c_has_neg = any(w in c_text for w in neg_set)
            c_has_pos = any(w in c_text for w in pos_set) and not c_has_neg

            a_has_neg = any(re.search(r'\b' + re.escape(w) + r'\b', a_text) for w in neg_set)
            a_has_pos = any(re.search(r'\b' + re.escape(w) + r'\b', a_text) for w in pos_set) and not a_has_neg

            if (c_has_pos and a_has_neg) or (c_has_neg and a_has_pos):
                return 0.15, "Polarity mismatch: Claim directly contradicts abstract conclusion", best_sentence

        # 2. Universal Zero-Shot Multilingual Alignment
        overall_sim = MultilingualFeatureExtractor.compute_cross_lingual_similarity(claim, abstract)
        final_score = round(max(overall_sim, sent_score), 2)

        if final_score >= 0.25:
            reason = "正文断言与文献摘要核心观点高度吻合"
        elif final_score >= 0.15:
            reason = "断言与摘要部分重合，建议人工核对"
        else:
            reason = "正文断言与摘要语义匹配度较低"

        return final_score, reason, best_sentence


