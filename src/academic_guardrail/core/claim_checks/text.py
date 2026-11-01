"""Source-preserving text units and deliberately small comparison anchors."""

from dataclasses import dataclass
import re
import unicodedata

from academic_guardrail.core.models import SemanticFinding

# Only recognized surface forms are compared. Unknown predicates are not inferred.
UP = r"increas(?:e|es|ed|ing)|improv(?:e|es|ed|ing)|enhanc(?:e|es|ed|ing)|elevat(?:e|es|ed)|promot(?:e|es|ed)|rais(?:e|es|ed)|accelerat(?:e|es|ed)|stimulat(?:e|es|ed)"
DOWN = r"reduc(?:e|es|ed|ing)|decreas(?:e|es|ed|ing)|lower(?:s|ed|ing)?|inhibit(?:s|ed|ing)?|prevent(?:s|ed)?|slow(?:s|ed)? down|attenuat(?:e|es|ed)"
OTHER = r"caus(?:e|es|ed)|lead(?:s)? to|led to|result(?:s|ed)? in|associat(?:e|es|ed)|correlat(?:e|es|ed)|link(?:s|ed)?"
PREDICATE = re.compile(rf"\b(?:{UP}|{DOWN}|{OTHER})\b|提高|提升|增加|促进|加速|降低|减少|抑制|阻碍|导致|造成|相关", re.I)
COPULA = re.compile(r"\b(?:is|are|was|were)\b|为|是", re.I)
STOP = set("a an the this that these those it they we our their its and or to of in on with by for from at as be been being is are was were do does did has have had not no never cannot can will may might could would should only also just significantly statistically directly markedly slightly substantially robust proposed experimental results demonstrate demonstrated show showed found study research clinical trial trials evidence there impossible all some many most any each every under after before across among during within percent percentage points mg g kg ml l ms s second seconds rate rates level levels therapy application based mechanism".split())
ALIASES = {"drug": "treatment", "drugs": "treatment", "treatments": "treatment",
           "algorithm": "method", "model": "method", "methods": "method",
           "death": "mortality", "deaths": "mortality", "overall": "total", "all-cause": "total",
           "patients": "patient", "networks": "network", "cells": "cell"}
CN_NOISE = re.compile(r"本研究发现|研究表明|实证分析表明|本研究|实证分析|不仅|不但|而且|该|这|的|了|使|将|并未|没有|未曾|未能|尚未|不|未|显著|明显|可能")
STOP -= {"rate", "rates", "level", "levels", "therapy"}
STOP |= {"failed", "fails", "than", "less", "more", "least", "approximately", "about", "around"}
ALIASES.update({"rates": "rate", "levels": "level", "therapy": "treatment"})
OBSERVATION_TIME = re.compile(r"\b(?:after|before|at|within|during|for)\s+\d+(?:\.\d+)?\s+(?:days?|weeks?|months?|years?|hours?)\b|\d+(?:\.\d+)?\s*(?:天|周|个月|年)(?:后|内|时)")


@dataclass(frozen=True)
class TextUnit:
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class Relation:
    subject: str
    predicate: str
    outcome: str
    predicate_start: int


def normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).replace("’", "'").replace("−", "-").lower()
    value = re.sub(r"\bcan't\b", "cannot", value)
    value = re.sub(r"\bwon't\b", "will not", value)
    value = re.sub(r"\b([a-z]+)n't\b", r"\1 not", value)
    value = re.sub(r"\\(?:cite|citep|citet|parencite)\*?(?:\[[^\]]*\])*\{[^{}]*\}", " ", value)
    value = re.sub(r"\[\s*\d+(?:\s*[,–—-]\s*\d+)*\s*\]", " ", value)
    return " ".join(value.split())


def different_languages(first: str, second: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", first)) != bool(re.search(r"[\u4e00-\u9fff]", second))


def sentence_units(text: str, *, split_semicolons: bool = True) -> list[TextUnit]:
    """Keep decimal points and return exact original substrings."""
    boundaries = [0]
    punctuation = r"[。！？!?；;]" if split_semicolons else r"[。！？!?]"
    for match in re.finditer(punctuation + r"|\.(?!\d)(?=\s|$)|\n\s*\n", text):
        prefix = text[:match.start()]
        if match.group() == "." and re.search(r"\b(?:Dr|Mr|Ms|Mrs|Prof|e\.g|i\.e|vs)$", prefix, re.I):
            continue
        boundaries.append(match.end())
    boundaries.append(len(text))
    return _units_from_boundaries(text, boundaries)


def _units_from_boundaries(text: str, boundaries: list[int]) -> list[TextUnit]:
    units = []
    for start, end in zip(boundaries, boundaries[1:]):
        segment = text[start:end]
        left = start + len(segment) - len(segment.lstrip())
        right = start + len(segment.rstrip())
        if right > left:
            units.append(TextUnit(text[left:right], left, right))
    return units


def clause_units(text: str) -> list[TextUnit]:
    """Split adversative clauses without moving any source coordinates."""
    units = []
    separator = re.compile(r"(?<!\d),(?!\d)|，|\b(?:although|however|whereas|while|but(?: also)?)\b|虽然|但是|然而|尽管|而且|反而", re.I)
    for sentence in sentence_units(text):
        # A comma does not sever a conditional/population modifier from its
        # assertion. Keep the complete sentence when attachment is uncertain.
        conditional = r"\b(?:if|unless|when|only in|only under|only when)\b|^(?:in|among|under)\b|如果|若|仅在|仅对|^在"
        if re.search(conditional, normalize(sentence.text)) or OBSERVATION_TIME.search(normalize(sentence.text)):
            units.append(sentence)
            continue
        start = 0
        fragments = []
        for match in separator.finditer(sentence.text):
            segment = sentence.text[start:match.start()]
            offset = sentence.start + start
            if segment.strip():
                left = offset + len(segment) - len(segment.lstrip())
                fragments.append(TextUnit(segment.strip(), left, left + len(segment.strip())))
            start = match.end()
        segment = sentence.text[start:]
        if segment.strip():
            left = sentence.start + start + len(segment) - len(segment.lstrip())
            fragments.append(TextUnit(segment.strip(), left, left + len(segment.strip())))
        # Commas around an apposition are not boundaries between assertions.
        # Keep the sentence if splitting would leave a fragment without its
        # own subject/predicate/outcome. Explicit contrast clauses keep the
        # existing local-negation behavior ("Although X ..., Y ...").
        contrast = re.search(r"\b(?:although|however|whereas|while|but)\b|虽然|但是|然而|尽管|而且|反而", sentence.text, re.I)
        incomplete = any(not (item := relation(fragment.text)) or
                         not anchor_tokens(item.subject) or not anchor_tokens(item.outcome)
                         for fragment in fragments)
        if len(fragments) > 1 and not contrast and incomplete:
            units.append(sentence)
        else:
            units.extend(fragments)
    return units


def relation(text: str) -> Relation | None:
    value = normalize(text)
    # Skip a leading participle such as 'Improved survival causes ...'. It has
    # no subject and must not hide the later causal predicate.
    match = next((m for m in PREDICATE.finditer(value) if anchor_tokens(value[:m.start()])), None)
    match = match or COPULA.search(value)
    if not match:
        return None
    outcome = value[match.end():]
    outcome = re.split(r"\b(?:in|among|under|across|after|before|during|within)\b|在", outcome, maxsplit=1)[0]
    subject = re.sub(r"^(?:in|among|under)\b[^,]+,\s*", "", value[:match.start()])
    return Relation(subject, match.group(), outcome, match.start())


def anchor_tokens(text: str) -> set[str]:
    value = normalize(text)
    value = PREDICATE.sub(" ", value)
    value = COPULA.sub(" ", value)
    english = {ALIASES.get(word, word) for word in re.findall(r"[a-z][a-z0-9_-]*", value) if word not in STOP}
    # Preserve short study-arm labels; the article 'a' in Drug A is an ID.
    english.update("id:" + m.group(1) for m in re.finditer(r"\b(?:drug|treatment|group|method|model|cohort|arm)\s+([a-z]|\d+)\b", value))
    chinese = CN_NOISE.sub("", "".join(re.findall(r"[\u4e00-\u9fff]+", value)))
    grams = {chinese[i:i + 2] for i in range(max(0, len(chinese) - 1))}
    return english | grams


def overlap(first: set[str], second: set[str]) -> float:
    return len(first & second) / min(len(first), len(second)) if first and second else 0.0


def target_mismatch(claim: str, evidence: str) -> bool:
    """Reject known subject/outcome mismatches before polarity comparisons."""
    first, second = relation(claim), relation(evidence)
    if first and second:
        for a, b in ((first.subject, second.subject), (first.outcome, second.outcome)):
            left, right = anchor_tokens(a), anchor_tokens(b)
            ids_a, ids_b = {s for s in left if s.startswith("id:")}, {s for s in right if s.startswith("id:")}
            if ids_a and ids_b and ids_a != ids_b:
                return True
            if left and right and overlap(left, right) < 0.35:
                return True
    left, right = anchor_tokens(claim), anchor_tokens(evidence)
    return bool(left and right and overlap(left, right) < 0.20)


def comparison_uncertain(claim: str, evidence: str) -> bool:
    """Overlapping words do not resolve different metric or subject modifiers."""
    first, second = relation(claim), relation(evidence)
    if not first or not second:
        return normalize(claim).rstrip(".。") != normalize(evidence).rstrip(".。")
    subjects = anchor_tokens(first.subject), anchor_tokens(second.subject)
    outcomes = anchor_tokens(first.outcome), anchor_tokens(second.outcome)
    if not all(subjects):
        return True
    return any(a != b for a, b in (subjects, outcomes))


def finding(code: str, category: str, message: str, claim: str, evidence: str,
            conflict: bool = False) -> SemanticFinding:
    return SemanticFinding(code=code, category=category, message=message,
                           severity="CONFLICT" if conflict else "REVIEW",
                           claim_text=claim, evidence_text=evidence)
