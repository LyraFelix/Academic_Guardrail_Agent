"""Retrieve comparable text, then run bounded, inspectable wording checks.

Similarity is a retrieval aid. Neither a high score nor TEXT_ALIGNED establishes
scientific support. Unknown constructions stay available for human review.
"""

from dataclasses import dataclass
import re

from academic_guardrail.core.claim_checks.numbers import check_numbers, quantities
from academic_guardrail.core.claim_checks.polarity import check_polarity, direction, negated, predicate_key
from academic_guardrail.core.claim_checks.scope import check_scope
from academic_guardrail.core.claim_checks.text import (
    clause_units, comparison_uncertain, different_languages, finding,
    normalize, relation, sentence_units, target_mismatch,
)
from academic_guardrail.core.models import ClaimAssessment, EvidencePassage, SemanticFinding
from academic_guardrail.core.config import GuardrailConfig
from academic_guardrail.core.passages import locate_excerpt
from academic_guardrail.core.semantic_matcher import SemanticMatcher
from academic_guardrail.core.text_similarity import ACADEMIC_SYNONYMS, UniversalLexicalMatcher


@dataclass
class Candidate:
    text: str
    passage: EvidencePassage
    score: float
    engine: str
    findings: list[SemanticFinding]

    def attach_source(self, findings: list[SemanticFinding]) -> list[SemanticFinding]:
        for item in findings:
            item.evidence_location = locate_excerpt(self.passage, item.evidence_text)
            item.evidence_source = self.passage.source_kind
        return findings


def compound_claim(text: str) -> bool:
    """Multiple asserted outcomes need individual citations/checks."""
    value = normalize(text)
    if len(sentence_units(text)) > 1:
        return True
    if re.search(r"\b(?:and|but|whereas)\b|并且|且|而且", value):
        return True
    return False


class ClaimEvaluator:
    """Separate candidate retrieval, rule findings and the final review state."""

    def __init__(self, use_embeddings: bool = True):
        self.semantic_matcher = SemanticMatcher(use_embeddings=use_embeddings)

    def _similarity(self, claim: str, text: str) -> tuple[float, str]:
        semantic, engine = self.semantic_matcher.compute_similarity_with_engine(claim, text)
        lexical = UniversalLexicalMatcher.compute_lexical_similarity(claim, text)
        return round(max(0.0, min(1.0, (semantic + lexical) / 2)), 2), engine

    def split_sentences(self, text: str) -> list[str]:
        return [unit.text for unit in sentence_units(text)]

    def find_best_matching_sentence(self, claim: str, abstract: str) -> tuple[str, float]:
        """Compatibility retrieval helper; its score is not a semantic verdict."""
        ranked = [(unit.text, self._similarity(claim, unit.text)[0])
                  for unit in sentence_units(abstract)] if claim else []
        return max(ranked, key=lambda item: item[1]) if ranked else ("", 0.0)

    def assess(self, claim: str, evidence: str) -> ClaimAssessment:
        return self.assess_passages(claim, [EvidencePassage(text=evidence, source_kind="PROVIDED_TEXT")])

    def assess_passages(self, claim: str, passages: list[EvidencePassage]) -> ClaimAssessment:
        candidates = []
        for passage in passages:
            for unit in clause_units(passage.text):
                score, engine = self._similarity(claim, unit.text)
                candidates.append(Candidate(unit.text, passage, score, engine, []))
        if not claim.strip() or not candidates:
            return ClaimAssessment(state="INSUFFICIENT_EVIDENCE", message="缺少断言或可用参考文本。")
        candidates.sort(key=lambda item: item.score, reverse=True)

        # Cross-language embeddings retrieve text, but these rules cannot verify
        # that predicates, units and qualifiers translate faithfully.
        same_language = [c for c in candidates if not different_languages(claim, c.text)]
        if not same_language:
            best = candidates[0]
            best.findings = [finding("LANGUAGE_COMPARISON_UNAVAILABLE", "EVIDENCE",
                                     "跨语言文字需要人工核对翻译；相似度不能代替逐项语义检查。", claim, best.text)]
            return self._assessment("REVIEW_REQUIRED", best, best.attach_source(best.findings))

        comparable = [c for c in same_language if c.score >= GuardrailConfig.CLAIM_RETRIEVAL_MIN_SCORE
                      and not target_mismatch(claim, c.text)]
        if not comparable:
            best = same_language[0]
            best.findings = [finding("TARGET_MISMATCH", "EVIDENCE",
                                     "未找到主体与结果对应的片段；不能借用其他对象或指标的方向判断冲突。", claim, best.text)]
            return self._assessment("INSUFFICIENT_EVIDENCE", best, best.attach_source(best.findings))

        for candidate in comparable:
            candidate.findings = candidate.attach_source(self._check_pair(claim, candidate.text))

        best = comparable[0]
        aligned = [c for c in comparable if not c.findings]
        conflicts = [c for c in comparable if any(f.severity == "CONFLICT" for f in c.findings)]
        disagreement = (aligned[0], conflicts[0]) if aligned and conflicts else None
        if not disagreement and len(conflicts) > 1:
            # Both fragments can differ from the claim and from each other.
            for candidate in conflicts[1:]:
                if any(f.severity == "CONFLICT" for f in self._check_pair(conflicts[0].text, candidate.text)):
                    disagreement = (conflicts[0], candidate)
                    break
        if disagreement:
            # Keep both quotes with their own coordinates. Similarity must not
            # silently discard conflicting evidence.
            findings = []
            for candidate in disagreement:
                item = finding("EVIDENCE_DISAGREEMENT", "EVIDENCE",
                               "可比片段给出不同表述，请结合研究条件核对，未按最高相似度挑选结论。", claim, candidate.text)
                findings.extend(candidate.attach_source([item]))
            findings.extend(f for c in comparable for f in c.findings)
            return self._assessment("REVIEW_REQUIRED", best, findings)

        findings = [f for c in comparable for f in c.findings]
        if conflicts:
            best = conflicts[0]
        state = ("POTENTIAL_CONFLICT" if conflicts else
                 "REVIEW_REQUIRED" if findings else "TEXT_ALIGNED")
        if compound_claim(claim):
            findings.extend(best.attach_source([finding("COMPOUND_CLAIM", "EVIDENCE",
                                    "断言包含多个结果或数量，请拆成单独论断逐项核对；一个匹配片段不能覆盖整句。", claim, best.text)]))
            state = "REVIEW_REQUIRED"
        return self._assessment(state, best, findings)

    @staticmethod
    def _check_pair(claim: str, evidence: str) -> list[SemanticFinding]:
        scope = check_scope(claim, evidence)
        uncertain = comparison_uncertain(claim, evidence)
        first, second = relation(claim), relation(evidence)
        if first and second:
            known_directions = direction(first.predicate) and direction(second.predicate)
            if not known_directions and predicate_key(first.predicate) != predicate_key(second.predicate):
                uncertain = True
        changed_conditions = bool(scope) or uncertain
        polarity = check_polarity(claim, evidence)
        values_c = [(q.value, q.dimension, q.qualifier) for q in quantities(claim)]
        values_e = [(q.value, q.dimension, q.qualifier) for q in quantities(evidence)]
        negated_quantity = (values_c or values_e) and values_c != values_e and (negated(claim) or negated(evidence))
        findings = [*scope, *polarity, *check_numbers(claim, evidence, bool(changed_conditions or negated_quantity))]
        if uncertain:
            findings.append(finding("COMPARISON_UNCERTAIN", "EVIDENCE",
                                    "主体、谓词、指标或修饰语尚未完整对应，词语重合不足以确认语义可比。", claim, evidence))
        if negated_quantity:
            findings.append(finding("NEGATED_QUANTITY", "NUMBER",
                                    "数量命题带有否定且数值不同：不是某个数值不能解释为另一个数值的反证。", claim, evidence))
        if changed_conditions or negated_quantity:
            for item in findings:
                item.severity = "REVIEW"
        return findings

    @staticmethod
    def _assessment(state: str, best: Candidate, findings: list[SemanticFinding]) -> ClaimAssessment:
        messages = {
            "TEXT_ALIGNED": "已检查的文字与限定相符，仍需核对研究设计和全文；这不是论断真实性证明。",
            "POTENTIAL_CONFLICT": "发现可比文字中的具体差异，请根据证据原句复核。",
            "REVIEW_REQUIRED": "语义限定或可比性尚未确认，需要人工复核。",
            "INSUFFICIENT_EVIDENCE": "没有找到可用于这项论断的对应证据，不能据此判定论断为假。",
        }
        return ClaimAssessment(state=state, similarity_score=best.score, message=messages[state],
                               evidence_text=best.text, evidence_location=locate_excerpt(best.passage, best.text),
                               text_source=best.passage.source_kind, alignment_engine=best.engine,
                               findings=findings)

    def evaluate_alignment(self, claim: str, abstract: str) -> tuple[float, str, str, str, str]:
        """Legacy tuple shape; states now use ClaimAssessment's review vocabulary."""
        result = self.assess(claim, abstract)
        reasons = " ".join(item.message for item in result.findings)
        return (result.similarity_score, result.message + " " + reasons, result.evidence_text,
                result.state, result.alignment_engine)


class UniversalSyntacticNegationAnalyzer:
    """Compatibility wrapper for old callers; no abstract-wide polarity scan."""

    @staticmethod
    def is_sentence_negated(sentence, shared_stems=None):
        return negated(sentence)

    @staticmethod
    def check_negation_conflict(claim, text):
        return any(not target_mismatch(claim, unit.text) and
                   any(f.severity == "CONFLICT" for f in check_polarity(claim, unit.text))
                   for unit in clause_units(text))


MultilingualFeatureExtractor = UniversalLexicalMatcher
NegationScopeDetector = UniversalSyntacticNegationAnalyzer
SYNONYM_MAP = ACADEMIC_SYNONYMS
