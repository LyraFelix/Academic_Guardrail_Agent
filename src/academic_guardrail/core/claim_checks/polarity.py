"""Compare local predicate wording only after subject/outcome alignment."""

import re

from academic_guardrail.core.claim_checks.text import COPULA, DOWN, UP, finding, normalize, relation

UNCERTAIN = r"\b(?:no|insufficient|limited|lack of) evidence\b|\b(?:cannot|could not) (?:establish|confirm|determine)\b|尚无证据|没有证据|缺乏证据|未发现证据"
COMPLEX = r"\bnot (?:impossible|unlikely|without)\b|\b(?:cannot|can not) rule out\b|不能排除|并非不|不是不"
NONSIGNIFICANT = r"\b(?:not|no|failed to)\b.{0,30}\bsignificant(?:ly)?\b|未显著|无显著|不显著|未达到统计显著"


def direction(predicate: str) -> int:
    if re.fullmatch(UP, predicate) or predicate in {"提高", "提升", "增加", "促进", "加速"}:
        return 1
    if re.fullmatch(DOWN, predicate) or predicate in {"降低", "减少", "抑制", "阻碍"}:
        return -1
    return 0


def negated(text: str) -> bool:
    value = normalize(text)
    value = re.sub(r"\bnot (?:only|just)\b|不仅|不但", "", value)
    item = relation(value)
    if item is None:
        return False
    # A local window avoids borrowing a later clause's negation.
    stop = item.predicate_start
    if COPULA.fullmatch(item.predicate):
        # Copular negation follows 'is/was', unlike 'does not reduce'.
        stop += len(item.predicate) + 15
    prefix = value[max(0, item.predicate_start - 60):stop]
    return bool(re.search(r"\b(?:not|no|never|cannot|without|failed to|fails to)\b|没有|未曾|未能|并未|无法|未|不", prefix))


def predicate_key(predicate: str) -> str:
    for pattern, label in ((r"caus\w*|lead(?:s)? to|led to|result(?:s|ed)? in|导致|造成", "cause"),
                           (r"associat\w*|correlat\w*|link\w*|相关", "association")):
        if re.fullmatch(pattern, predicate):
            return label
    if COPULA.fullmatch(predicate):
        return "copula"
    return predicate


def check_polarity(claim: str, evidence: str):
    c, e = normalize(claim), normalize(evidence)
    if re.search(COMPLEX, c) or re.search(COMPLEX, e):
        return [finding("COMPLEX_NEGATION", "NEGATION", "双重否定或排除性措辞需要人工解释，未按单个否定词翻转方向。", claim, evidence)]
    if re.search(UNCERTAIN, c) or re.search(UNCERTAIN, e):
        return [finding("UNCERTAIN_EVIDENCE", "NEGATION", "未发现证据等于证据不足，不能直接解释为效果不存在或方向相反。", claim, evidence)]
    if re.search(NONSIGNIFICANT, c) or re.search(NONSIGNIFICANT, e):
        return [finding("SIGNIFICANCE_UNCERTAINTY", "NEGATION", "统计不显著不能简化成没有效果；请核对效应量、区间和原文条件。", claim, evidence)]
    first, second = relation(c), relation(e)
    if not first or not second:
        return []
    a, b = direction(first.predicate), direction(second.predicate)
    negative_a, negative_b = negated(c), negated(e)
    same_predicate = (a == b != 0) or predicate_key(first.predicate) == predicate_key(second.predicate)
    if same_predicate and negative_a != negative_b:
        return [finding("NEGATION_DIFFERENCE", "NEGATION", "对应对象和结果的谓词出现肯定/否定差异，请核对原文。", claim, evidence, conflict=True)]
    if a and b and a != b:
        if negative_a or negative_b:
            return [finding("NEGATED_OPPOSITE_DIRECTION", "NEGATION", "否定增加不等于减少，否定减少也不等于增加；两种措辞不能简单翻转比较。", claim, evidence)]
        return [finding("DIRECTION_DIFFERENCE", "NEGATION", "对应对象和结果出现相反的方向用词，请核对适用条件。", claim, evidence, conflict=True)]
    return []
