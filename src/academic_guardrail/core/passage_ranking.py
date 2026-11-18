"""Rank whole raw passages from one paper; structure contributes scoped context."""

import math
import re
from dataclasses import dataclass

from academic_guardrail.core.passage_structure import passage_structures
from academic_guardrail.core.search_view import search_view, whole_term_pattern


@dataclass
class _Matches:
    spans: list[list[tuple[int, int]]]
    nearby_phrases: set[int]
    shingles: set[tuple[str, ...]]


def _search_queries(terms):
    queries, seen = [], set()
    for term in terms:
        key = search_view(term).text.strip()
        if key in seen:
            continue
        seen.add(key)
        pattern = whole_term_pattern(key, normalized=True)
        # A phrase with all its words nearby can boost an already matched
        # passage. A partial word or number cannot seed a hit.
        parts = ()
        if re.fullmatch(r"[a-z]{2,}(?: [a-z]{2,}){1,3}", key):
            words = key.split()
            if len(set(words)) == len(words):
                parts = tuple(whole_term_pattern(word, normalized=True) for word in words)
        queries.append((pattern, parts))
    return queries


def _nearby_phrase(view, parts):
    # Move the right edge across the text. Remember the latest occurrence of
    # each word whose end is already inside the window (either order is fine).
    events = sorted((end, start, word) for word, pattern in enumerate(parts)
                    for start, end in view.spans(pattern))
    latest = {}
    for end, start, word in events:
        latest[word] = max(start, latest.get(word, -1))
        if len(latest) == len(parts) and end - min(latest.values()) <= 120:
            return True
    return False


def _passage_matches(passage, queries, weighted):
    view = search_view(passage.text)
    spans = [view.spans(pattern) for pattern, _ in queries]
    near, shingles = set(), set()
    if weighted and any(spans):
        for term, (_, parts) in enumerate(queries):
            if parts and not spans[term] and _nearby_phrase(view, parts):
                near.add(term)
        words = re.findall(r"\w+", view.text.replace("\u00ad", ""))
        shingles = set(zip(words, words[1:], words[2:])) or {tuple(words)}
    return _Matches(spans, near, shingles)


def _literal_order(matches):
    counts = [[len(spans) for spans in match.spans] for match in matches]
    return sorted((i for i, row in enumerate(counts) if any(row)),
                  key=lambda i: (-sum(bool(n) for n in counts[i]), -sum(counts[i]), i))


def _scores(matches, candidates):
    n = len(matches)
    weights = []
    for term in range(len(matches[0].spans)):
        frequency = sum(bool(match.spans[term]) or term in match.nearby_phrases for match in matches)
        weights.append(math.log1p((n - frequency + 0.5) / (frequency + 0.5)))
    scores = {}
    for i in candidates:
        match = matches[i]
        # BM25-style inverse passage frequency and saturating term counts.
        counts = [len(spans) for spans in match.spans]
        score = sum(weight * (2 * count / (1 + count)) for weight, count in zip(weights, counts))
        score += sum(0.5 * weights[term] for term in match.nearby_phrases)
        scores[i] = score
    return weights, scores


def _in_range(match, lo, hi):
    return {term for term, spans in enumerate(match.spans)
            if any(lo <= start and end <= hi for start, end in spans)}


def _structure_links(passages, matches, weights):
    """Only matches inside an actual label/row/body range participate in its link."""
    bonuses, links = {}, {}
    for group in passage_structures(passages):
        anchor = group.anchor
        label = _in_range(matches[anchor], group.label_start, group.label_end)
        scoped = {i: _in_range(matches[i], lo, hi) for i, lo, hi in group.regions}
        if not scoped or not any(scoped.values()):
            continue
        label_weight = sum(weights[term] for term in label)
        # Choose the part with most other query information under this heading.
        # If only the label matched, show the first available continuation.
        body = max(scoped, key=lambda j: (sum(weights[t] for t in scoped[j] - label),
                                          j != anchor, -abs(j - anchor)))
        for i, terms in scoped.items():
            if not terms:
                continue
            bonus = label_weight
            if label and i == anchor:
                bonus += sum(weights[t] for t in scoped[body] - terms)
            bonuses[i] = max(bonuses.get(i, 0), bonus)
            if group.kind == "table":
                indices = tuple(scoped)  # Keep caption, column labels and rows together.
            else:
                endpoint = body if label else i
                indices = tuple(j for j in scoped if anchor <= j <= max(i, endpoint))
            priority = (bool(label), sum(weights[t] for t in terms), -abs(i - anchor))
            if i not in links or priority > links[i][0]:
                links[i] = (priority, indices)
    return bonuses, {i: indices for i, (_, indices) in links.items()}


def rank_passages(passages, terms, mode, max_hits):
    """Return actual hit indices first, then other candidates in base-score order."""
    queries = _search_queries(terms)
    weighted = mode != "normalized"
    matches = [_passage_matches(passage, queries, weighted) for passage in passages]
    candidates = _literal_order(matches)
    if not weighted or not candidates:
        return candidates, {}
    weights, scores = _scores(matches, candidates)
    links = {}
    if mode == "structural":
        bonuses, links = _structure_links(passages, matches, weights)
        for i in candidates:
            scores[i] += bonuses.get(i, 0)
    ordered = sorted(candidates, key=lambda i: -scores[i])

    # Suppress near-verbatim repeats and passages already returned as immediate
    # neighbors. Lower-scored candidates can still fill the three available hits.
    remaining, hits = ordered.copy(), []
    novelty = {i: 1.0 for i in remaining}
    while remaining and len(hits) < max_hits:
        hit = max(remaining, key=lambda i: scores[i] * novelty[i])
        remaining.remove(hit)
        hits.append(hit)
        selected_words = matches[hit].shingles
        for i in remaining:
            words = matches[i].shingles
            similarity = len(selected_words & words) / len(selected_words | words)
            factor = 1 - similarity
            if abs(i - hit) == 1:
                factor *= 0.5
            novelty[i] = min(novelty[i], factor)
    return hits + remaining, links
