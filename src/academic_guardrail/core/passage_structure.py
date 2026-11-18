"""Bounded links between printed headings/captions and original passage ranges."""

import re
from dataclasses import dataclass

from academic_guardrail.core.models import EvidencePassage


# A structural link spans at most four consecutive passage chunks per side.
# Physical PDFs also stop at the page edge. Plain text has no physical page IDs.
_MAX_DISTANCE = 3
_CAPTION = re.compile(r"^\s*((?:table|tab\.|figure|fig\.|表|图)\s*"
                      r"(?:[a-z]?\d+(?:\.\d+)*[a-z]?|[ivxlcdm]+))"
                      r"\s*(?:[:.：．–—]|$)", re.I)
_NUMBERED = re.compile(r"^\s*(?:#{1,6}\s+|\d+(?:\.\d+)*[.)]?\s+)(?=[A-Z\u3400-\u9fff])")
_RUN_IN = re.compile(r"^\s*((?:[A-Z][\w -]{0,48}\s+)?(?:settings?|setup|protocol|configuration|"
                     r"design|results?|procedure|training|evaluation|analysis))\s*[.:]\s+", re.I)
_NUMBER = re.compile(r"(?<!\w)[+−-]?\d+(?:[.,]\d+)*")
_PROSE = re.compile(r"\b(?:the|is|are|was|were|has|have|we|our|this|that|shows?)\b", re.I)


@dataclass(frozen=True)
class Structure:
    kind: str
    anchor: int
    label_start: int
    label_end: int
    # (passage index, local raw start, local raw end), always in source order.
    regions: tuple[tuple[int, int, int], ...]


@dataclass(frozen=True)
class _Line:
    index: int
    start: int
    end: int
    text: str


def _same_page(passages, first, second):
    a, b = passages[first].location, passages[second].location
    return bool(a and b and a.file_path == b.file_path and a.page == b.page)


def _label(line: _Line, standalone: bool):
    text = line.text.strip()
    left = line.start + len(line.text) - len(line.text.lstrip())
    caption = _CAPTION.match(text)
    if caption:
        name = caption.group(1)
        kind = "table" if name.lower().startswith(("tab", "表")) else "figure"
        return kind, left, left + caption.end(1)
    run_in = _RUN_IN.match(text)
    if run_in and text[0].isupper() and not _PROSE.search(run_in.group(1)):
        return "heading", left, left + run_in.end(1)
    if len(text) > 110 or len(text.split()) > 15:
        return None
    if _NUMBERED.match(text):
        return "heading", left, left + len(text)
    # A plain one-line paragraph is a heading only when it looks like a label.
    if (standalone and text and text[0].isupper() and len(text.split()) <= 7
            and not re.search(r"[\d.,;:!?|\t]", text) and not _PROSE.search(text)):
        return "heading", left, left + len(text)
    return None


def _table_line(line: _Line):
    """Distinguish tabular data/column labels from neighboring prose."""
    text = line.text.strip()
    if ("|" in text or "\t" in text) and len(text) < 240:
        return "data"
    if not text or len(text) > 130 or _PROSE.search(text):
        return None
    words = text.split()
    if len(words) > 14 or text.endswith((".", "?", "!", "。")):
        return None
    if _NUMBER.search(text):
        return "data"
    if len(words) <= 8 and all(word.strip("-*/()").isalpha() for word in words):
        return "header"
    return None


def _table_side(lines, labels, passages, position, step):
    anchor = lines[position].index
    blocks, kinds = [], set()
    i = position + step
    while 0 <= i < len(lines):
        line = lines[i]
        if abs(line.index - anchor) > _MAX_DISTANCE or not _same_page(passages, anchor, line.index):
            break
        label = labels.get(i)
        if label:
            if label[0] != "heading" or _NUMBERED.match(line.text) or _RUN_IN.match(line.text):
                break
            # A plain heading after a top-captioned table starts another
            # section. A column header before the first data row is legitimate.
            if step == 1 and "data" in kinds and _table_line(line) == "header":
                break
        kind = _table_line(line)
        if not kind:
            break
        blocks.append(line)
        kinds.add(kind)
        i += step
    return blocks, kinds


def _table_regions(lines, labels, passages, position):
    before, kinds_before = _table_side(lines, labels, passages, position, -1)
    after, kinds_after = _table_side(lines, labels, passages, position, 1)
    # Captions can be above or below a table. Require visible data and prefer a
    # side with both labels and data. Two equally plausible sides are ambiguous.
    def strength(kinds):
        if "data" not in kinds:
            return 0
        return 2 if "header" in kinds else 1

    left, right = strength(kinds_before), strength(kinds_after)
    chosen = []
    if left > right:
        chosen = before
    elif right > left:
        chosen = after
    bounds = {}
    for line in sorted([lines[position], *chosen], key=lambda item: (item.index, item.start)):
        start = bounds.get(line.index, (line.start, 0))[0]
        bounds[line.index] = (start, line.end)
    return tuple((index, start, end) for index, (start, end) in bounds.items())


def passage_structures(passages: list[EvidencePassage]) -> list[Structure]:
    """Ranges have tighter boundaries than the whole raw chunks ultimately shown."""
    lines, labels = [], {}
    for index, passage in enumerate(passages):
        found = list(re.finditer(r"[^\r\n]+", passage.text))
        for match in found:
            line = _Line(index, match.start(), match.end(), match.group())
            label = _label(line, len(found) == 1)
            if label:
                labels[len(lines)] = label
            lines.append(line)

    result = []
    positions = list(labels)
    for n, position in enumerate(positions):
        kind, start, end = labels[position]
        anchor = lines[position].index
        if kind == "table":
            regions = _table_regions(lines, labels, passages, position)
        elif kind == "figure":
            regions = ((anchor, start, lines[position].end),)
        else:
            next_label = lines[positions[n + 1]] if n + 1 < len(positions) else None
            blocks = []
            for i in range(anchor, min(len(passages), anchor + _MAX_DISTANCE + 1)):
                if i != anchor and not _same_page(passages, anchor, i):
                    break
                lo = start if i == anchor else 0
                hi = len(passages[i].text)
                if next_label and i == next_label.index:
                    hi = next_label.start
                if hi > lo:
                    blocks.append((i, lo, hi))
                if next_label and i == next_label.index:
                    break
            regions = tuple(blocks)
        result.append(Structure(kind, anchor, start, end, regions))
    return result
