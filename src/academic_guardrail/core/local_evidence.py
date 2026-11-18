"""Bound a local follow-up to contextual hits in one pinned paper.

Identity selection belongs to LocalRefStore and the review service. This module
never resolves a new paper: it only reopens the absolute path in its snapshot.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from academic_guardrail.core.followup_models import LocalSearchResult, LocalSource
from academic_guardrail.core.models import EvidencePassage, PaperRecord
from academic_guardrail.core.passage_ranking import rank_passages
from academic_guardrail.core.ref_store import LocalRefStore
from academic_guardrail.core.search_view import whole_term_pattern


SourceStatus = Literal["CURRENT", "CHANGED", "MISSING", "UNREADABLE"]
MAX_NEW_CHARACTERS = 18000
RetrievalMode = Literal["original", "normalized", "ranked", "structural"]


@dataclass(frozen=True)
class PassageSelection:
    """Indices refer to the caller's original passages; ranks are best first."""
    ranked_indices: tuple[int, ...]
    hit_indices: tuple[int, ...]
    context_indices: tuple[int, ...]
    character_count: int


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def snapshot_bytes(path_string: str, sha256: str) -> tuple[bytes | None, SourceStatus]:
    """Read a pinned manuscript or paper only at its original canonical path."""
    try:
        path = Path(path_string)
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
    if hashlib.sha256(raw_bytes).hexdigest() != sha256:
        return None, "CHANGED"
    return raw_bytes, "CURRENT"


def source_status(source: LocalSource) -> SourceStatus:
    """Report current raw-file status without changing the saved source."""
    return snapshot_bytes(source.path, source.sha256)[1]


def _current_source_bytes(source: LocalSource) -> bytes:
    raw_bytes, status = snapshot_bytes(source.path, source.sha256)
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
        terms.append(term)
        patterns.append(whole_term_pattern(term))
    return terms, patterns


def select_local_passages(passages: list[EvidencePassage], search_terms: list[str], *,
                          mode: RetrievalMode = "structural", max_hits: int = 3) -> PassageSelection:
    """Select from one already-parsed paper without reading files or calling a model.

    Original reproduces the literal ranking. Normalized changes spelling only.
    Ranked adds inverse passage frequency, bounded proximity and deduplication.
    Structural also links a matching heading/caption with scoped body/table text.
    All modes reserve whole hits and their immediate neighbors first. Structural
    then fits complete linked groups, highest-ranked hit first. Characters count
    unique raw passages in this lookup, before parent-packet evidence deduplication.
    """
    terms, patterns = _query_patterns(search_terms)
    if type(max_hits) is not int or not 1 <= max_hits <= 3:
        raise ValueError("max_hits must be an integer between one and three.")
    if mode not in {"original", "normalized", "ranked", "structural"}:
        raise ValueError(f"Unknown local retrieval mode: {mode}")
    if len({p.location.file_path for p in passages if p.location}) > 1:
        raise ValueError("A local lookup requires passages from one source file.")

    links = {}
    if mode == "original":
        ranked = []
        for index, passage in enumerate(passages):
            counts = [len(pattern.findall(passage.text)) for pattern in patterns]
            coverage = sum(count > 0 for count in counts)
            if coverage:
                ranked.append((-coverage, -sum(counts), index))
        order = [index for _, _, index in sorted(ranked)]
    else:
        order, links = rank_passages(passages, terms, mode, max_hits)
    hits = order[:max_hits]
    context = {j for i in hits for j in range(max(0, i - 1), min(len(passages), i + 2))}
    characters = sum(len(passages[i].text) for i in context)
    # At the current 1200-character parser limit the three base neighborhoods
    # together consume at most 10800 characters. Never truncate them silently.
    if characters > MAX_NEW_CHARACTERS:
        raise ValueError("Complete hit context exceeds the local lookup character budget.")
    for i in hits:
        additions = set(links.get(i, ())) - context
        cost = sum(len(passages[j].text) for j in additions)
        if characters + cost <= MAX_NEW_CHARACTERS:
            context.update(additions)
            characters += cost
    return PassageSelection(tuple(order), tuple(hits), tuple(sorted(context)), characters)


def search_local_evidence(source: LocalSource, search_terms: list[str],
                          *, max_hits: int = 3) -> LocalSearchResult:
    """Search the pinned article and return original passages in document order."""
    raw_bytes = _current_source_bytes(source)
    record = LocalRefStore().extract_paper_record(source.path, source_bytes=raw_bytes)
    if record is None:
        raise ValueError("The pinned local source no longer has readable article text.")
    if _text_sha256(record.fulltext) != source.text_sha256:
        raise ValueError("Extracted text differs from the pinned text snapshot.")
    if (record.title, record.doi) != (source.title, source.doi):
        raise ValueError("Extracted paper identity differs from the pinned source.")

    selection = select_local_passages(record.passages, search_terms, max_hits=max_hits)
    return LocalSearchResult(query_terms=[term.strip() for term in search_terms],
                             passages=[record.passages[i] for i in selection.context_indices],
                             matched_passages=len(selection.hit_indices),
                             total_passages=len(record.passages))
