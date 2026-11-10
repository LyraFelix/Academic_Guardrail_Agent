"""Bound a local follow-up to one original paper and literal, contextual hits.

Identity selection belongs to LocalRefStore and the review service. This module
never resolves a new paper: it only reopens the absolute path in its snapshot.
"""

import hashlib
import re
from pathlib import Path
from typing import Literal

from academic_guardrail.core.followup_models import LocalSearchResult, LocalSource
from academic_guardrail.core.models import PaperRecord
from academic_guardrail.core.ref_store import LocalRefStore


SourceStatus = Literal["CURRENT", "CHANGED", "MISSING", "UNREADABLE"]
MAX_NEW_CHARACTERS = 18000
# Han ideographs do not need spaces between words. Keep other Unicode letters,
# digits and underscores as token characters, including accented Latin letters.
_HAN_RANGES = (r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
               r"\U00020000-\U0002fa1f\U00030000-\U000323af")
_HAN_CHARACTER = re.compile(f"[{_HAN_RANGES}]")
_NON_HAN_WORD_CHARACTER = rf"[^\W{_HAN_RANGES}]"


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _source_bytes_and_status(source: LocalSource) -> tuple[bytes | None, SourceStatus]:
    """Read once; the caller can parse the very bytes whose hash was checked."""
    try:
        path = Path(source.path)
        if not path.is_absolute():
            return None, "UNREADABLE"
        resolved = path.resolve(strict=True)
        # A replaced symlink must not silently point this snapshot at a new file.
        if resolved != path:
            return None, "CHANGED"
        if not resolved.is_file():
            return None, "UNREADABLE"
        raw_bytes = resolved.read_bytes()
    except FileNotFoundError:
        return None, "MISSING"
    except (OSError, RuntimeError, ValueError):
        return None, "UNREADABLE"
    if hashlib.sha256(raw_bytes).hexdigest() != source.sha256:
        return None, "CHANGED"
    return raw_bytes, "CURRENT"


def source_status(source: LocalSource) -> SourceStatus:
    """Report current raw-file status without changing the saved source."""
    return _source_bytes_and_status(source)[1]


def _current_source_bytes(source: LocalSource) -> bytes:
    raw_bytes, status = _source_bytes_and_status(source)
    if status != "CURRENT" or raw_bytes is None:
        raise ValueError(f"Local source is {status}; the pinned paper cannot be used.")
    return raw_bytes


def ensure_current_source(source: LocalSource) -> None:
    """Block a judgment if its original file is no longer the pinned source."""
    _current_source_bytes(source)


def snapshot_for_record(record: PaperRecord, refs_root: str) -> LocalSource:
    """Bind an already identity-matched record to its original bytes and text.

    A legacy record without a raw-byte hash must be indexed again. Hashing its
    current path alone could bind old extracted evidence to a newer file.
    """
    root = Path(refs_root).resolve()
    selected = Path(record.filepath).resolve()
    if not root.is_dir():
        raise ValueError("The local reference root must be an existing directory.")
    if not selected.is_relative_to(root):
        raise ValueError("The selected local paper is outside the reference root.")
    if not record.source_sha256 or not record.fulltext.strip():
        raise ValueError("The paper has no original source hash/text snapshot; index it again.")
    source = LocalSource(path=str(selected), sha256=record.source_sha256,
                         text_sha256=_text_sha256(record.fulltext),
                         title=record.title, doi=record.doi)
    ensure_current_source(source)
    return source


def _query_patterns(search_terms: list[str]) -> tuple[list[str], list[re.Pattern]]:
    """Match Han substrings and whole other tokens, without segmenting words.

    A Han character at either query edge needs no boundary. Beside another edge,
    Han characters delimit Latin/numeric tokens (for example, 中文IL6 or 降低25%).
    Other Unicode word characters still prevent partial-word matches. Punctuation
    is literal, and numeric fragments of decimals/thousands remain excluded.
    """
    if not isinstance(search_terms, list) or not 1 <= len(search_terms) <= 6:
        raise ValueError("Provide between one and six literal search terms.")
    terms, patterns, seen = [], [], set()
    for value in search_terms:
        if not isinstance(value, str):
            raise ValueError("Each search term must be text.")
        term = value.strip()
        if not 1 <= len(term) <= 100 or not any(char.isalnum() for char in term):
            raise ValueError("Each search term must contain a word/number and at most 100 characters.")
        normalized = term.casefold()
        if normalized in seen:
            raise ValueError("Search terms must be distinct after trimming and ignoring case.")
        seen.add(normalized)
        # Escape every supplied character: no regex operators, aliases or stemming.
        left = "" if _HAN_CHARACTER.fullmatch(term[0]) else rf"(?<!{_NON_HAN_WORD_CHARACTER})"
        right = "" if _HAN_CHARACTER.fullmatch(term[-1]) else rf"(?!{_NON_HAN_WORD_CHARACTER})"
        pattern = left + re.escape(term) + right
        if term[0].isdigit():
            pattern = r"(?<!\d[.,])" + pattern
        if term[-1].isdigit():
            pattern += r"(?![.,]\d)"
        terms.append(term)
        patterns.append(re.compile(pattern, re.IGNORECASE))
    return terms, patterns


def search_local_evidence(source: LocalSource, search_terms: list[str],
                          *, max_hits: int = 3) -> LocalSearchResult:
    """Return up to three lexical hits with their immediate passage neighbors.

    Ranking uses the number of distinct literal terms matched, then occurrence
    count, then original document order. The selected whole passages are emitted
    in document order; overlapping context is included once. ``matched_passages``
    counts selected hit passages, while ``total_passages`` counts all searched
    passages. The existing parser excludes bibliography and preserves the actual
    abstract as part of the searchable article text.
    """
    terms, patterns = _query_patterns(search_terms)
    if type(max_hits) is not int or not 1 <= max_hits <= 3:
        raise ValueError("max_hits must be an integer between one and three.")
    raw_bytes = _current_source_bytes(source)
    record = LocalRefStore().extract_paper_record(source.path, source_bytes=raw_bytes)
    if record is None:
        raise ValueError("The pinned local source no longer has readable article text.")
    if _text_sha256(record.fulltext) != source.text_sha256:
        raise ValueError("Extracted text differs from the pinned text snapshot.")
    if (record.title, record.doi) != (source.title, source.doi):
        raise ValueError("Extracted paper identity differs from the pinned source.")

    ranked = []
    for index, passage in enumerate(record.passages):
        counts = [len(pattern.findall(passage.text)) for pattern in patterns]
        coverage = sum(count > 0 for count in counts)
        if coverage:
            ranked.append((-coverage, -sum(counts), index))
    ranked.sort()
    selected_hits = [index for _, _, index in ranked[:max_hits]]
    selected_indices = set()
    for index in selected_hits:
        selected_indices.update(range(max(0, index - 1), min(len(record.passages), index + 2)))
    passages = [record.passages[index] for index in sorted(selected_indices)]
    # Current chunks are <= 1200 characters, so three hits with neighbors fit.
    # Fail explicitly if that parser contract changes; never cut off context.
    if sum(len(passage.text) for passage in passages) > MAX_NEW_CHARACTERS:
        raise ValueError("Complete hit context exceeds the local lookup character budget.")
    return LocalSearchResult(query_terms=terms, passages=passages,
                             matched_passages=len(selected_hits),
                             total_passages=len(record.passages))
