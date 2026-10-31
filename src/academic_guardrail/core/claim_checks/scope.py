"""Causal strength and explicitly stated populations, times and qualifiers."""

import re

from academic_guardrail.core.claim_checks.text import DOWN, UP, OBSERVATION_TIME, finding, normalize

ASSOCIATION = r"\b(?:associat\w*|correlat\w*|linked? to)\b|相关|关联"
CAUSAL = rf"\b(?:caus\w*|lead(?:s)? to|led to|result(?:s|ed)? in|{UP}|{DOWN})\b|导致|造成|提高|降低|减少|增加|提升"
MODAL = r"\b(?:may|might|could|can|possibly|potentially|perhaps)\b|可能|或许|或可"
UNIVERSAL = r"\b(?:all(?!-cause)|every|always|everyone|universally|any)\b|所有|全部|总是|均有效|一定"
LIMITED = r"\b(?:some|subset|selected|occasionally)\b|部分|某些|少数"
POPULATIONS = {"mouse": r"\b(?:mice|mouse|murine)\b|小鼠", "human": r"\bhumans?\b|人类",
               "adult": r"\badults?\b|成年人", "child": r"\b(?:children|child|pediatric)\b|儿童",
               "in_vitro": r"\bin vitro\b|体外", "in_vivo": r"\bin vivo\b|体内"}
CONDITION = re.compile(r"\b(?:only (?:in|under|when|among)|under|in this|in the studied|on the tested)\b[^.;]{1,90}|仅(?:在|对)[^。；]{1,40}")
EXPLICIT_SCOPE = re.compile(r"\b(?:in|among|under|across|when|if|unless)\b[^,.;!?]{1,120}|(?:在|仅对)[^，。；！？]{1,60}")


def scope_phrases(text: str) -> set[str]:
    """Keep literal qualifiers outside the small population vocabulary too."""
    phrases = set()
    for match in EXPLICIT_SCOPE.finditer(text):
        phrase = match.group().strip()
        # Prefix 'In mice, ...' ends at the comma; suffix scope stays intact.
        phrases.add(phrase)
    return phrases


def check_scope(claim: str, evidence: str):
    c, e = normalize(claim), normalize(evidence)
    results = []
    non_assertive = r"[?？]|\b(?:hypothes\w*|if|unless|whether)\b|假设|是否|如果|尚待验证"
    if re.search(non_assertive, c) or re.search(non_assertive, e):
        results.append(finding("NON_ASSERTIVE_TEXT", "EVIDENCE", "疑问、假设或条件表达尚未构成确定陈述，需要核对上下文。", claim, evidence))
    if re.search(CAUSAL, c) and not re.search(ASSOCIATION, c) and re.search(ASSOCIATION, e):
        results.append(finding("CAUSAL_OVERSTATEMENT", "CAUSALITY", "正文使用因果或效果措辞，原文只表达关联；相关性不能直接升级为因果结论。", claim, evidence))
    if not re.search(MODAL, c) and re.search(MODAL, e):
        results.append(finding("MODALITY_STRENGTHENED", "SCOPE", "正文省略了可能性限定，把可能发生写成确定发生。", claim, evidence))
    if re.search(UNIVERSAL, c) and not re.search(UNIVERSAL, e):
        results.append(finding("SCOPE_STRENGTHENED", "SCOPE", "正文扩展为所有、始终等全称范围，原文没有相同的全称限定。", claim, evidence))
    elif not re.search(LIMITED, c) and re.search(LIMITED, e):
        results.append(finding("SCOPE_OMITTED", "SCOPE", "原文限定为部分对象，正文未保留该限制。", claim, evidence))
    population_c = {name for name, pattern in POPULATIONS.items() if re.search(pattern, c)}
    population_e = {name for name, pattern in POPULATIONS.items() if re.search(pattern, e)}
    if population_c != population_e:
        code = "POPULATION_CHANGED" if population_c and population_e else "SCOPE_OMITTED"
        results.append(finding(code, "SCOPE", "两段文字的实验对象或适用人群未对应，请勿直接推广结论。", claim, evidence))
    phrases_c, phrases_e = scope_phrases(c), scope_phrases(e)
    if phrases_c != phrases_e:
        code = "POPULATION_CHANGED" if phrases_c and phrases_e else "SCOPE_OMITTED"
        results.append(finding(code, "SCOPE", "明确写出的适用对象或条件短语不同，需要逐项核对限定。", claim, evidence))
    times_c, times_e = set(OBSERVATION_TIME.findall(c)), set(OBSERVATION_TIME.findall(e))
    if times_c != times_e:
        results.append(finding("TIME_SCOPE_CHANGED", "SCOPE", "观察时点或持续时间发生变化；不同时间下的数值不能直接当作矛盾。", claim, evidence))
    conditions_c, conditions_e = set(CONDITION.findall(c)), set(CONDITION.findall(e))
    if conditions_c != conditions_e and (conditions_c or conditions_e):
        results.append(finding("SCOPE_OMITTED", "SCOPE", "原文和正文的条件限定未对应，请核对仅在何种情形下成立。", claim, evidence))
    return results
