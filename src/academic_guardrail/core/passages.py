"""Paragraph chunks retain exact substrings and never cross a physical PDF page."""

import re

from academic_guardrail.core.models import EvidencePassage
from academic_guardrail.core.text_extraction import ExtractedText


def build_passages(document: ExtractedText, start: int = 0, end: int | None = None,
                   max_chars: int = 1200) -> list[EvidencePassage]:
    end = len(document.text) if end is None else end
    page_bounds = [start, *(p for p in document.page_starts if start < p < end), end]
    passages = []
    for left, right in zip(page_bounds, page_bounds[1:]):
        # Blank lines delimit paragraphs; long paragraphs split at whitespace.
        for paragraph in re.finditer(r".+?(?=\n[ \t]*\n|\Z)", document.text[left:right], re.S):
            pos, limit = left + paragraph.start(), left + paragraph.end()
            while pos < limit:
                stop = min(pos + max_chars, limit)
                if stop < limit:
                    space = document.text.rfind(" ", pos + max_chars // 2, stop)
                    if space > pos:
                        stop = space
                text = document.text[pos:stop]
                trimmed = text.strip()
                if trimmed:
                    begin = pos + len(text) - len(text.lstrip())
                    finish = pos + len(text.rstrip())
                    passages.append(EvidencePassage(text=document.text[begin:finish], source_kind="LOCAL_FULLTEXT",
                                                     location=document.location(begin, finish)))
                pos = stop
                while pos < limit and document.text[pos].isspace():
                    pos += 1
    return passages


def locate_excerpt(passage: EvidencePassage, excerpt: str):
    """Return an exact location only when the evaluator selected a real substring."""
    if passage.location is None:
        return None
    offset = passage.text.find(excerpt)
    if offset < 0:
        return None
    location = passage.location.model_copy(deep=True)
    location.char_start += offset
    location.char_end = location.char_start + len(excerpt)
    if location.line is not None:
        location.line += passage.text.count("\n", 0, offset)
    return location
