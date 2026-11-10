"""Index user-supplied papers, resolve identity, and retain traceable body passages."""

import hashlib
import re
from pathlib import Path
from typing import Optional

from academic_guardrail.core.exceptions import ParserError
from academic_guardrail.core.identifiers import DOI_REGEX, clean_doi
from academic_guardrail.core.models import Citation, PaperRecord, ParseDiagnostic
from academic_guardrail.core.passages import build_passages
from academic_guardrail.core.ref_resolver import ReferenceResolver
from academic_guardrail.core.text_extraction import read_document

REFERENCE_SECTION = re.compile(r"(?im)^[ \t]*(?:#{1,6}\s*|\d+[.)]?\s+)?(?:references|bibliography|参考文献)[ \t]*(?:[:：]|$)")
NUMBERED_REFERENCE = re.compile(r"(?im)^[ \t]*\[\d+\][ \t]+[^\n]*(?:\.\s+|10\.\d{4,9}/|\[[JMDCRNPS]\])")
ABSTRACT = re.compile(r"(?im)^[ \t]*(?:abstract|摘要)[ \t]*[:：]?[ \t]*\n?")
SECTION = re.compile(r"(?im)^[ \t]*(?:\d+[.)]?\s+)?(?:introduction|methods|results|discussion|引言|方法|结果|讨论)\b")


class LocalRefStore:
    """No full-text or filename hit may stand in for the paper's own identity."""

    def __init__(self, refs_dir: Optional[str] = None, excluded_paths=()):
        self.refs_dir = refs_dir
        self.records: list[PaperRecord] = []
        self.diagnostics: list[ParseDiagnostic] = []
        self.resolver = ReferenceResolver()
        if refs_dir:
            root = Path(refs_dir).resolve()
            if not root.is_dir():
                self.diagnostics.append(ParseDiagnostic(code="LOCAL_DIRECTORY_UNREADABLE", message=f"参考文献目录不存在或不是文件夹：{refs_dir}"))
                return
            excluded = {Path(path).resolve() for path in excluded_paths}
            for path in sorted(root.rglob("*")):
                if path.is_file() and path.suffix.lower() in {".txt", ".md", ".docx", ".pdf"} and path.resolve() not in excluded:
                    if not path.resolve().is_relative_to(root):
                        self.diagnostics.append(ParseDiagnostic(
                            code="LOCAL_FILE_OUTSIDE_ROOT", message=f"参考文献路径指向目录以外：{path}"))
                        continue
                    record = self.extract_paper_record(str(path))
                    if record:
                        self.records.append(record)

    def extract_paper_record(self, path: str, *, source_bytes: bytes | None = None) -> Optional[PaperRecord]:
        """Use the same identity/body parser for indexing and a pinned-file lookup."""
        selected_path = Path(path)
        return self._extract_paper_record(path, selected_path.name, selected_path.suffix.lower(),
                                          source_bytes=source_bytes)

    def _extract_paper_record(self, path: str, filename: str, ext: str,
                              *, source_bytes: bytes | None = None) -> Optional[PaperRecord]:
        try:
            raw_bytes = Path(path).read_bytes() if source_bytes is None else source_bytes
            document = read_document(path, source_bytes=raw_bytes)
        except (ParserError, OSError) as exc:
            self.diagnostics.append(ParseDiagnostic(code="LOCAL_FILE_UNREADABLE", message=str(exc)))
            return None
        self.diagnostics.extend(document.diagnostics)
        text = document.text
        if not text.strip():
            self.diagnostics.append(ParseDiagnostic(code="LOCAL_FILE_EMPTY", message=f"文件没有可提取文本：{path}"))
            return None
        # An explicit bibliography heading is stronger than a wrapped in-text
        # citation such as "[38] showed ..." at the start of a PDF text line.
        heading = REFERENCE_SECTION.search(text)
        unheaded = NUMBERED_REFERENCE.search(text) if heading is None else None
        body_end = heading.start() if heading else unheaded.start() if unheaded else len(text)
        body = text[:body_end]
        lines = list(re.finditer(r"(?m)^.*\S.*$", body))
        if not lines:
            return None
        title = lines[0].group().strip().lstrip("# ")
        abstract_marker = ABSTRACT.search(body)
        section = SECTION.search(body)
        first_break = re.search(r"\n[ \t]*\n", body)
        header_end = min([1500, len(body), *([first_break.start()] if first_break else []), *([abstract_marker.start()] if abstract_marker else []),
                          *([section.start()] if section else [])])
        header = body[:header_end]
        # Only the front matter is eligible. A DOI in references or a retrieved
        # passage cannot identify the containing article.
        doi_region_end = min([1500, len(body), *([abstract_marker.start()] if abstract_marker else []),
                              *([section.start()] if section else [])])
        # A labeled DOI can follow a blank line within front matter. Restrict
        # this extension to identifier lines, not prose that cites another DOI.
        doi_lines = re.finditer(r"(?im)^[ \t]*(?:(?:related[ \t]+)?doi[ \t]*[:：]?\s+|(?:related[ \t]+)?doi[:：]|https?://(?:dx\.)?doi\.org/|(?=10\.\d{4,9}/))[^\n]*", body[:doi_region_end])
        doi_text = header + "\n" + "\n".join(line.group() for line in doi_lines)
        dois = {clean_doi(match.group()).lower() for match in DOI_REGEX.finditer(doi_text)}
        doi = next(iter(dois)) if len(dois) == 1 else None
        if len(dois) > 1:
            self.diagnostics.append(ParseDiagnostic(code="AMBIGUOUS_LOCAL_DOI", message=f"文件首页元数据包含多个 DOI，未选择其一：{path}"))
        year_match = re.search(r"\b(19\d{2}|20\d{2})\b", header)
        authors = []
        if len(lines) > 1 and lines[1].start() < header_end:
            author_line = lines[1].group().strip()
            if len(author_line) < 150 and not re.search(r"abstract|摘要|doi|university|大学|^\d{4}$", author_line, re.I):
                authors = [value.strip() for value in re.split(r"[,;，；]", author_line) if value.strip()]
        abstract, abstract_location = "", None
        if abstract_marker:
            tail = body[abstract_marker.end():]
            stop = re.search(r"\n\s*\n", tail)
            next_section = SECTION.search(tail)
            finish = min([len(tail), *([stop.start()] if stop else []),
                          *([next_section.start()] if next_section else [])])
            abstract = tail[:finish].strip()
            if abstract:
                start = abstract_marker.end() + len(tail[:finish]) - len(tail[:finish].lstrip())
                abstract_location = document.location(start, start + len(abstract))
        # Keep the real abstract distinct from the full body; no first-500-char
        # fallback can masquerade as an abstract.
        text_start = abstract_marker.end() if abstract_marker else (section.start() if section else first_break.end() if first_break else lines[0].end())
        return PaperRecord(filename=filename, filepath=document.file_path, title=title,
                           authors=authors, year=int(year_match.group()) if year_match else None,
                           doi=doi, doi_candidates=sorted(dois), abstract=abstract,
                           abstract_location=abstract_location, fulltext=text,
                           source_sha256=hashlib.sha256(raw_bytes).hexdigest(),
                           passages=build_passages(document, text_start, body_end))

    def select_candidate(self, citation: Citation) -> Optional[dict]:
        """Unlike find_match, this keeps ambiguity visible to the service."""
        target_doi = self.resolver.normalize_doi(citation.doi)
        exact, candidates = [], []
        for record in self.records:
            own_doi = self.resolver.normalize_doi(record.doi)
            if target_doi and own_doi is None and not record.doi_candidates:
                # A known target DOI cannot be replaced by a title-only guess.
                continue
            if target_doi and record.doi_candidates and target_doi not in record.doi_candidates:
                continue
            if target_doi and own_doi and target_doi != own_doi:
                continue
            candidate = record.model_dump()
            candidate["source"] = record.filepath
            if target_doi and own_doi == target_doi:
                # A supplied title that strongly disagrees is a metadata conflict.
                if citation.title and self.resolver._calc_hybrid_title_sim(citation.title, record.title) < 0.5:
                    continue
                exact.append(candidate)
                continue
            # Known author/year conflicts cannot vanish through score renormalization.
            if citation.authors and record.authors and self.resolver._calc_author_score(citation, candidate) == 0:
                continue
            if citation.year and record.year and abs(citation.year - record.year) > 1:
                continue
            candidates.append(candidate)
        if exact:
            best = exact[0]
            best.update(match_score=1.0, match_confidence="HIGH", resolution_metadata={"resolver": "local_exact_doi"})
            if len(exact) > 1:
                best.update(is_uncertain=True, match_confidence="UNCERTAIN", ambiguous_candidates=[
                    {"title": item["title"], "doi": item["doi"], "source": item["filepath"], "score": 1.0} for item in exact])
            return best
        best = self.resolver.select_best_candidate(citation, candidates, deduplicate=False)
        if best and len(best.get("doi_candidates", [])) > 1:
            best.update(is_uncertain=True, match_confidence="UNCERTAIN", ambiguous_candidates=[
                {"title": best["title"], "doi": doi, "source": best["filepath"], "score": best["match_score"]}
                for doi in best["doi_candidates"]])
        return best

    def find_match(self, citation: Citation) -> Optional[dict]:
        match = self.select_candidate(citation)
        return match if match and not match.get("is_uncertain") else None

    def find_abstract_for_citation(self, title: str, raw_text: str):
        """Compatibility adapter. New service code uses the structured passages."""
        match = self.find_match(Citation(id="local", title=title or raw_text, raw_text=raw_text))
        if not match:
            return None
        return (match.get("abstract") or match.get("fulltext") or "").strip(), match["filename"], match["match_score"]
