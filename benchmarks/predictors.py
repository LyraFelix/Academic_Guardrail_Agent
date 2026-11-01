"""Predictors see only InputCase, never gold labels or rationale indices."""

from academic_guardrail.providers.claim_eval import ClaimEvaluator
from academic_guardrail.core.text_similarity import UniversalLexicalMatcher
from benchmarks.schema import Prediction

METHOD_CONFIGS = {
    "guardrail": {"embeddings": False, "description": "frozen phase-three rules"},
    "overlap": {"embeddings": False, "threshold": 0.50, "description": "lexical sentence retrieval only"},
    "always_review": {"embeddings": False, "description": "always REVIEW_REQUIRED"},
}


def sentence_ids_for_excerpt(sentences, excerpt, *, full_sentences=False):
    """Locate the first exact substring, matching production excerpt behavior.

    Default IDs overlap the excerpt; full_sentences requires complete coverage.
    Neither is an official SciFact rationale prediction.
    """
    if not excerpt:
        return []
    text = "\n\n".join(sentences)
    start = text.find(excerpt)
    if start < 0:
        raise ValueError("Evidence excerpt is not an exact input substring")
    end, offset, selected = start + len(excerpt), 0, []
    for index, sentence in enumerate(sentences):
        stop = offset + len(sentence)
        included = start <= offset and stop <= end if full_sentences else start < stop and offset < end
        if included:
            selected.append(index)
        offset = stop + 2
    return selected


def make_predictor(method):
    if method not in METHOD_CONFIGS:
        raise ValueError(f"Unknown method: {method}")
    evaluator = ClaimEvaluator(use_embeddings=False) if method == "guardrail" else None

    def predict(case):
        if method == "always_review":
            return Prediction(id=case.id, state="REVIEW_REQUIRED", engine="always_review")
        if method == "overlap":
            ranked = [(UniversalLexicalMatcher.compute_lexical_similarity(case.claim, sentence), sentence)
                      for sentence in case.sentences]
            score, excerpt = max(ranked, key=lambda pair: pair[0]) if ranked else (0.0, "")
            return Prediction(id=case.id, score=score, evidence_text=excerpt, engine="lexical_only",
                              state="TEXT_ALIGNED" if score >= METHOD_CONFIGS[method]["threshold"] else "INSUFFICIENT_EVIDENCE",
                              sentence_ids=sentence_ids_for_excerpt(case.sentences, excerpt))
        assessment = evaluator.assess(case.claim, "\n\n".join(case.sentences))
        return Prediction(id=case.id, state=assessment.state, score=assessment.similarity_score,
                          evidence_text=assessment.evidence_text, engine=assessment.alignment_engine,
                          sentence_ids=sentence_ids_for_excerpt(case.sentences, assessment.evidence_text),
                          findings=[item.model_dump(mode="json") for item in assessment.findings])

    return predict
