"""Claim Evaluator with Antonym & Polarity Inversion Logic for SciFact NLI Alignment."""

import re
import difflib
from typing import Tuple, Dict, Any

OPPOSITE_PAIRS = [
    ({"increase", "increases", "increasing", "promote", "promotes", "elevate", "elevates", "accelerate", "accelerates"},
     {"inhibit", "inhibits", "decrease", "decreases", "reduce", "reduces", "prevent", "prevents", "slow down", "did not lower", "did not reduce", "not increase", "no effect"}),
    
    ({"reduce", "reduces", "reducing", "lower", "lowers", "prevent", "prevents"},
     {"did not lower", "did not reduce", "elevate", "elevates", "increase", "increases", "accelerate"}),
]


class ClaimEvaluator:
    """Evaluates alignment and detects polarity contradictions between user claim and paper abstract."""

    def evaluate_alignment(self, claim: str, abstract: str) -> Tuple[float, str]:
        if not claim or not abstract:
            return 0.0, "Missing claim or abstract"

        c_text = claim.lower().strip()
        a_text = abstract.lower().strip()

        # 1. Check for explicit polarity contradiction / antonyms
        for pos_set, neg_set in OPPOSITE_PAIRS:
            c_has_pos = any(re.search(r'\b' + re.escape(w) + r'\b', c_text) for w in pos_set)
            a_has_neg = any(re.search(r'\b' + re.escape(w) + r'\b', a_text) for w in neg_set)

            c_has_neg = any(re.search(r'\b' + re.escape(w) + r'\b', c_text) for w in neg_set)
            a_has_pos = any(re.search(r'\b' + re.escape(w) + r'\b', a_text) for w in pos_set)

            if (c_has_pos and a_has_neg) or (c_has_neg and a_has_pos):
                return 0.15, "Polarity mismatch: Claim directly contradicts abstract conclusion"

        # 2. Token overlap & difflib sequence similarity
        c_words = set(re.findall(r'\b\w{3,}\b', c_text))
        a_words = set(re.findall(r'\b\w{3,}\b', a_text))

        if not c_words:
            return 0.0, "Empty claim tokens"

        overlap = c_words.intersection(a_words)
        overlap_ratio = len(overlap) / len(c_words)

        seq_sim = difflib.SequenceMatcher(None, c_text, a_text).ratio()
        final_score = round(0.7 * overlap_ratio + 0.3 * seq_sim, 2)

        if final_score >= 0.50:
            reason = "Strong semantic alignment with abstract"
        elif final_score >= 0.30:
            reason = "Partial alignment, manual review recommended"
        else:
            reason = "Low semantic alignment with abstract"

        return final_score, reason
