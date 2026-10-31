"""Lexical ranking helpers retained for retrieval, never semantic verdicts."""

import re
import difflib

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
