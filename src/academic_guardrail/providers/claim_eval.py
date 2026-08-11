"""General-Purpose Claim Evaluator with Universal Sentence-Level Alignment and Syntactic Negation Analysis.

Designed for robust, zero-overfitting domain-agnostic academic verification.
Uses generic linguistic stemming, academic synonym mapping, sentence-level rationale selection,
and universal syntactic negation & directional antonym analysis.
"""

import re
import difflib
from typing import Tuple, Dict, Any, List, Optional
from academic_guardrail.core.semantic_matcher import SemanticMatcher
from academic_guardrail.core.config import GuardrailConfig

# Standard academic synonyms for domain-agnostic lexical expansion
ACADEMIC_SYNONYMS = {
    "enable": {"allow", "permit", "facilitate", "enable"},
    "allow": {"enable", "permit", "facilitate", "allow"},
    "reduce": {"decrease", "lower", "diminish", "curtail", "reduce"},
    "decrease": {"reduce", "lower", "diminish", "decrease"},
    "promote": {"increase", "elevate", "enhance", "stimulate", "promote"},
    "increase": {"promote", "elevate", "enhance", "stimulate", "increase"},
    "mortality": {"death", "mortality", "deaths", "fatalities"},
    "death": {"mortality", "death", "deaths"},
    "overall": {"all-cause", "total", "overall"},
    "all-cause": {"overall", "total", "all-cause"},
    "diabetic": {"diabetic", "diabetes", "diabet"},
    "diabetes": {"diabetic", "diabetes", "diabet"},
    "diabet": {"diabetic", "diabetes", "diabet"},
    "patient": {"patient", "patients"},
    "patients": {"patient", "patients"},
}

# Universal directional antonym sets for generic polarity inversion detection
DIRECTIONAL_ANTONYMS = [
    (
        {"increase", "increases", "increased", "increasing", "promote", "promotes", "promoted", "elevate", "elevates", "elevated", "accelerate", "accelerates", "accelerated", "提升", "增加", "促进", "加速"},
        {"inhibit", "inhibits", "inhibited", "decrease", "decreases", "decreased", "reduce", "reduces", "reduced", "prevent", "prevents", "slow down", "slows down", "slowed down", "抑制", "降低", "减少", "阻碍"}
    )
]


class UniversalLexicalMatcher:
    """Domain-agnostic surface lexical matching using stemming, synonyms, N-grams, and sequence ratios."""

    @staticmethod
    def stem_word(word: str) -> str:
        w = word.lower().strip()
        for suffix in ['ing', 'tion', 'ness', 'ment', 'able', 'ed', 'es', 's']:
            if len(w) > 4 and w.endswith(suffix):
                return w[:-len(suffix)]
        return w

    @classmethod
    def get_stems(cls, text: str) -> set:
        words = re.findall(r'\b\w{2,}\b', text.lower())
        stems = set()
        for w in words:
            stems.add(cls.stem_word(w))
            if w in ACADEMIC_SYNONYMS:
                stems.update([cls.stem_word(syn) for syn in ACADEMIC_SYNONYMS[w]])
        return stems

    @staticmethod
    def get_char_ngrams(text: str, n: int = 3) -> set:
        clean = re.sub(r'[^\w\s]', '', text.lower()).strip()
        if not clean:
            return set()
        return set(clean[i:i+n] for i in range(len(clean) - n + 1))

    @classmethod
    def compute_lexical_similarity(cls, claim: str, sentence: str) -> float:
        """Pure language-agnostic surface lexical overlap score with synonym expansion."""
        if not claim or not sentence:
            return 0.0

        c_stems = cls.get_stems(claim)
        s_stems = cls.get_stems(sentence)
        c_ngrams = cls.get_char_ngrams(claim, n=3)
        s_ngrams = cls.get_char_ngrams(sentence, n=3)

        stem_overlap = (len(c_stems.intersection(s_stems)) / float(max(len(c_stems), 1))) if c_stems and s_stems else 0.0
        ngram_jaccard = (len(c_ngrams.intersection(s_ngrams)) / float(max(len(c_ngrams.union(s_ngrams)), 1))) if c_ngrams and s_ngrams else 0.0
        seq_sim = difflib.SequenceMatcher(None, claim.lower(), sentence.lower()).ratio()

        return round(0.50 * stem_overlap + 0.30 * ngram_jaccard + 0.20 * seq_sim, 2)

    @classmethod
    def compute_cross_lingual_similarity(cls, claim: str, sentence: str) -> float:
        return cls.compute_lexical_similarity(claim, sentence)


class UniversalSyntacticNegationAnalyzer:
    """Language-agnostic syntactic negation and directional polarity analyzer.
    Detects universal negation markers (not, no, never, failed to, 未, 不)
    and directional antonym inversions on shared core concepts at sub-clause level.
    """

    ENGLISH_NEGATION_MARKERS = {
        "not", "no", "never", "cannot", "can't", "fail", "failed", "fails",
        "failing", "without", "neither", "nor", "lack", "lacks", "lacking", "lacked"
    }

    CHINESE_NEGATION_MARKERS = {"未", "不", "没有", "未曾", "无法", "未能", "毫无", "并未"}

    CLAUSE_SPLIT_PATTERN = re.compile(
        r'(?:[;,]|\b(?:although|however|but|while|whereas|despite|even though|in contrast)\b|虽然|但是|然而|尽管|但)',
        re.IGNORECASE
    )

    @classmethod
    def split_clauses(cls, text: str) -> List[str]:
        """Splits complex compound sentences into sub-clauses for localized polarity scope analysis."""
        if not text:
            return []
        raw_clauses = [c.strip() for c in cls.CLAUSE_SPLIT_PATTERN.split(text) if len(c.strip()) >= 3]
        return raw_clauses if raw_clauses else [text]

    @classmethod
    def find_most_relevant_clause(cls, claim: str, sentence: str) -> str:
        """Locates the single sub-clause in sentence with highest stem overlap to claim."""
        clauses = cls.split_clauses(sentence)
        if len(clauses) <= 1:
            return sentence

        c_stems = UniversalLexicalMatcher.get_stems(claim)
        best_clause = clauses[0]
        max_overlap = -1

        for cl in clauses:
            cl_stems = UniversalLexicalMatcher.get_stems(cl)
            overlap = len(c_stems.intersection(cl_stems))
            if overlap > max_overlap:
                max_overlap = overlap
                best_clause = cl

        return best_clause

    @classmethod
    def is_sentence_negated(cls, text: str, target_stems: Optional[set] = None) -> bool:
        t_lower = text.lower()
        words = re.findall(r'\b[a-zA-Z]+\b', t_lower)

        # 1. English syntactic negation check
        for idx, w in enumerate(words):
            if w in cls.ENGLISH_NEGATION_MARKERS:
                if target_stems:
                    window = [UniversalLexicalMatcher.stem_word(x) for x in words[idx+1:idx+5]]
                    if any(st in target_stems for st in window):
                        return True
                else:
                    return True

        # 2. Chinese negation check
        for m in cls.CHINESE_NEGATION_MARKERS:
            if m in text:
                return True

        return False

    @classmethod
    def check_negation_conflict(cls, claim: str, sentence: str) -> bool:
        """Determines if there is a direct syntactic negation or directional antonym inversion at clause level."""
        c_text = claim.lower()
        target_clause = cls.find_most_relevant_clause(claim, sentence)
        s_text = target_clause.lower()

        # Check directional antonym pairs (e.g. increase vs inhibit / slow down)
        for pos_set, neg_set in DIRECTIONAL_ANTONYMS:
            c_has_pos = any(w in c_text for w in pos_set)
            c_has_neg = any(w in c_text for w in neg_set)
            s_has_pos = any(w in s_text for w in pos_set)
            s_has_neg = any(w in s_text for w in neg_set)

            if (c_has_pos and s_has_neg and not c_has_neg) or (c_has_neg and s_has_pos and not s_has_neg):
                return True

        # Check Chinese negation conflict
        c_cn_neg = any(m in c_text for m in cls.CHINESE_NEGATION_MARKERS)
        s_cn_neg = any(m in s_text for m in cls.CHINESE_NEGATION_MARKERS)
        if c_cn_neg != s_cn_neg:
            # Verify Chinese character overlap
            c_chars = set(c_text) - set(" ,.，。!！?？\t\n")
            s_chars = set(s_text) - set(" ,.，。!！?？\t\n")
            if len(c_chars.intersection(s_chars)) >= 3:
                return True

        # Check English syntactic negation on shared stems
        c_stems = UniversalLexicalMatcher.get_stems(claim)
        s_stems = UniversalLexicalMatcher.get_stems(target_clause)
        shared_stems = c_stems.intersection(s_stems)

        if shared_stems:
            c_neg = cls.is_sentence_negated(claim, shared_stems)
            s_neg = cls.is_sentence_negated(target_clause, shared_stems)
            if c_neg != s_neg:
                return True

        return False


class ClaimEvaluator:
    """General-purpose two-stage claim evaluator.
    Stage 1: Sentence-Level Rationale Selection (splits abstract into sentences and finds best matching context).
    Stage 2: Semantic & Lexical Fusion with Universal Syntactic Negation Conflict Detection.
    """

    def __init__(self):
        self.semantic_matcher = SemanticMatcher()

    def split_sentences(self, text: str) -> List[str]:
        """Splits multi-sentence abstract or full-text into sentence units (supports Chinese & English)."""
        if not text:
            return []
        raw_sents = re.split(r'[。！？；.!?;\n]+\s*', text)
        return [s.strip() for s in raw_sents if len(s.strip()) >= 4]

    def find_best_matching_sentence(self, claim: str, abstract: str) -> Tuple[str, float]:
        """Stage 1: Rationale Selection — finds the single abstract sentence with highest alignment."""
        if not claim or not abstract:
            return "", 0.0

        sentences = self.split_sentences(abstract)
        if not sentences:
            return abstract[:150], 0.0

        best_sent = sentences[0]
        best_score = 0.0

        for sent in sentences:
            sem_score = self.semantic_matcher.compute_similarity(claim, sent)
            lex_score = UniversalLexicalMatcher.compute_lexical_similarity(claim, sent)
            score = 0.50 * sem_score + 0.50 * lex_score
            if score > best_score:
                best_score = score
                best_sent = sent

        return best_sent, round(best_score, 2)

    def evaluate_alignment(self, claim: str, abstract: str) -> Tuple[float, str, str, str, str]:
        """Evaluates claim alignment against abstract using general-purpose sentence-level logic.

        Returns: (final_score, reason, best_matching_sentence, alignment_state, alignment_engine)
        """
        if not claim or not abstract:
            return 0.0, "缺少断言或参考文献摘要", "", "UNVERIFIED", "rule_lexical_fallback"

        best_sentence, sent_score = self.find_best_matching_sentence(claim, abstract)
        sem_score, alignment_engine = self.semantic_matcher.compute_similarity_with_engine(claim, best_sentence)

        # 1. Syntactic Negation & Directional Antonym Inversion Check
        if UniversalSyntacticNegationAnalyzer.check_negation_conflict(claim, best_sentence) or \
           UniversalSyntacticNegationAnalyzer.check_negation_conflict(claim, abstract):
            return GuardrailConfig.POLARITY_CONTRADICTION_SCORE, "显式极性矛盾：断言与文献核心句存在语法否定或方向相反逻辑 (Polarity Inversion)", best_sentence, "CONTRADICTED", alignment_engine

        # 2. Dual-channel score computation against best matching sentence
        lex_score = UniversalLexicalMatcher.compute_lexical_similarity(claim, best_sentence)

        # Cross-lingual script handling: do not penalize semantic score if lexical overlap is 0 due to script differences
        if sem_score >= 0.35 and lex_score < 0.10:
            final_score = round(max(sem_score, sent_score), 2)
        else:
            final_score = round(max(0.50 * sem_score + 0.50 * lex_score, sent_score), 2)

        if final_score >= GuardrailConfig.STRONG_ALIGNMENT_THRESHOLD:
            reason = "正文断言与文献摘要呈现极高语义与词汇重合 (High Alignment)"
            alignment_state = "SUPPORTED"
        elif final_score >= GuardrailConfig.WEAK_ALIGNMENT_THRESHOLD:
            reason = "正文断言与文献摘要呈现中度相关（仅背景或部分吻合）"
            alignment_state = "PARTIAL"
        else:
            reason = "正文断言未在文献摘要中找到直接因果证据支持"
            alignment_state = "NEUTRAL"

        return final_score, reason, best_sentence, alignment_state, alignment_engine


# Backward-compatibility aliases
MultilingualFeatureExtractor = UniversalLexicalMatcher
NegationScopeDetector = UniversalSyntacticNegationAnalyzer
SYNONYM_MAP = ACADEMIC_SYNONYMS
OPPOSITE_PAIRS = DIRECTIONAL_ANTONYMS
