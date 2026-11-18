"""Separate bibliography entries from each body occurrence, preserving source spans."""

import re
from bisect import bisect_left, bisect_right
from pathlib import Path
from urllib.parse import urlparse

from academic_guardrail.core.bibliography import group_end, literal_text, parse_bibtex
from academic_guardrail.core.exceptions import ParserError
from academic_guardrail.core.identifiers import DOI_REGEX, clean_doi, extract_doi
from academic_guardrail.core.models import Citation, ContextClaim, ParsedDocument, ParseDiagnostic
from academic_guardrail.core.text_extraction import ExtractedText, read_document

REFERENCE_HEADING = re.compile(r"(?im)^\s*#{0,6}\s*(?:references|bibliography|参考文献)\s*[:：]?\s*$")
REFERENCE_START = re.compile(r"(?m)^[ \t]*(?:\[(\d+)\]|(\d+)[.)])[ \t]+([^\n]+)")
NUMBER_MARKER = re.compile(r"\[\s*([\d\s,，\-–—]+)\s*\]")
CITE_COMMAND = re.compile(r"\\(?:cite|citep|citet|parencite|textcite|autocite|footcite)\*?\s*(?:\[[^\]]*\]\s*){0,2}\{([^{}]+)\}")
BIBITEM = re.compile(r"\\bibitem\s*(?:\[[^\]]*\]\s*)?\{([^{}]+)\}")
AUTHOR_SEPARATOR = r"(?:[,，;；]\s*(?:(?:and|&)\s+)?|\s+(?:and|&)\s+)"
INITIALLED_AUTHOR = r"(?:[A-Z]\.[ -]*)+(?:(?:de|del|da|van|von|der|la) )*[^\W\d_]+(?:[-'’][^\W\d_]+)*"
INITIALLED_NAMES = rf"{INITIALLED_AUTHOR}(?:{AUTHOR_SEPARATOR}{INITIALLED_AUTHOR})*"
INITIALLED_AUTHOR_LIST = re.compile(rf"^({INITIALLED_NAMES})\.\s+")
INVERTED_AUTHOR = r"[^.,，;；]+[,，]\s*(?:[A-Z]\.[ -]*)+"
INVERTED_NAMES = re.compile(rf"{INVERTED_AUTHOR}(?:{AUTHOR_SEPARATOR}{INVERTED_AUTHOR})*")
AUTHOR_DATE = re.compile(r"\((?:19|20)\d{2}[a-z]?\)\.\s+")
INVERTED_AUTHOR_SEPARATOR = re.compile(
    r"[;；]|[,，]\s*(?:and|&)\s+|\s+(?:and|&)\s+|[,，](?!\s*(?:[A-Z]\.[ -]*)+(?:[,，;；&]|$))")
ACADEMIC_ABBREVIATION = re.compile(
    r"\b(?:(?P<authors>et[ \t]+al)|e\.g|i\.e|figs?|eqs?|refs?|secs?|pp?|nos?(?=\.\s*\d)|"
    r"dr|mr|mrs|ms|prof|vs|cf)\.", re.I)
MARKDOWN_HEADING = re.compile(r"(?m)^ {0,3}#{1,6}[ \t]+[^\n]*(?:\n|$)")
SENTENCE_END = re.compile(r"(?<=[。！？])|(?<=[.!?])(?=\s|$)")
NONSPACE = re.compile(r"\S")
LINE_END = re.compile(r"[ \t]*\n")
CITED_PREDICATE = re.compile(r"\s*(?:[a-z]|指出|提出|报道|报告|发现|认为|表明|显示|证明|证实|描述|讨论|采用|使用|给出)")


def _mask(text: str) -> str:
    """Blank content without changing any line or character offset."""
    return re.sub(r"[^\n]", " ", text)


def _claim_boundaries(document: ExtractedText, body: str, marker_pattern: re.Pattern):
    """Index sentence and paragraph boundaries once, in the original coordinate system."""
    paragraph_breaks = {0, len(body), *document.paragraph_starts}
    paragraph_breaks.update(match.end() for match in re.finditer(r"\n[ \t]*\n", body))
    if Path(document.file_path).suffix.lower() == ".md":
        for heading in MARKDOWN_HEADING.finditer(body):
            paragraph_breaks.update(heading.span())
    paragraphs = sorted(paragraph_breaks)
    # A period in a citation's optional arguments (e.g. LaTeX [p. 2]) cannot end a claim.
    prose = marker_pattern.sub(lambda match: _mask(match.group()), body)
    abbreviations = set()
    for match in ACADEMIC_ABBREVIATION.finditer(prose):
        # 'et al.' can also finish a complete sentence before a new capitalized one.
        if match.group("authors"):
            limit = paragraphs[bisect_right(paragraphs, match.start())]
            following = NONSPACE.search(prose, match.end(), limit)
            if following is None or following.group().isupper():
                continue
        abbreviations.add(match.end())
    sentence_ends = [m.end() for m in SENTENCE_END.finditer(prose) if m.end() not in abbreviations]
    boundaries = {*paragraphs, *sentence_ends}
    attached = {}
    for marker in marker_pattern.finditer(body):
        start, end = marker.span()
        block = bisect_right(paragraphs, start)
        preceding = bisect_right(sentence_ends, start)
        # '[1] reports ...' is the subject of its own sentence. 'Result. [1]'
        # attaches backwards only within the same paragraph.
        continues = CITED_PREDICATE.match(prose, end, paragraphs[block])
        if preceding and not continues:
            previous = sentence_ends[preceding - 1]
            if previous > paragraphs[block - 1] and not prose[previous:start].strip():
                attached[start] = previous
                boundaries.add(end)
        newline = LINE_END.match(body, end)
        if newline and not continues:
            boundaries.add(newline.end())
    return sorted(boundaries), attached


def _number_keys(content: str) -> list[str]:
    keys = []
    for part in re.split(r"[,，]", content):
        bounds = re.split(r"[-–—]", part.strip())
        if len(bounds) == 1 and bounds[0].isdigit():
            keys.append(str(int(bounds[0])))
        elif len(bounds) == 2 and all(b.strip().isdigit() for b in bounds):
            start, end = map(int, bounds)
            if not 0 <= end - start < 1000:
                raise ValueError("Citation range is reversed or exceeds 1000 entries")
            keys.extend(str(number) for number in range(start, end + 1))
        else:
            raise ValueError("Malformed citation group")
    return list(dict.fromkeys(keys))


def _reference_fields(head: str) -> tuple[list[str], str]:
    """Recognize explicit author/date and initial-first forms before the numbered style."""
    date = AUTHOR_DATE.search(head)
    if date:
        author_field = head[:date.start()].strip()
        # A parenthesized year after an earlier title delimiter belongs to that title.
        if author_field and (not re.search(r"\.\s+", author_field) or INVERTED_NAMES.fullmatch(author_field)
                             or re.fullmatch(INITIALLED_NAMES, author_field.removesuffix("."))):
            if not re.search(r"\b[A-Z]\.$", author_field):
                author_field = author_field.removesuffix(".")
            return INVERTED_AUTHOR_SEPARATOR.split(author_field), head[date.end():]
    initialled = INITIALLED_AUTHOR_LIST.match(head)
    if initialled:
        return re.split(AUTHOR_SEPARATOR, initialled.group(1)), head[initialled.end():]
    # Numbered fixtures use both 'Smith J, Doe A. Title' and 'Alice Smith. Title'.
    fields = re.split(r"\.\s+", head, maxsplit=1)
    if len(fields) == 2:
        return re.split(r"[,;，；]\s*", fields[0]), fields[1]
    return [], head


def _reference(key: str, raw: str, content: str, document: ExtractedText, start: int, end: int) -> Citation:
    content = literal_text(content)
    head = re.split(r"\[[JMDCRNPS](?:/OL)?\]", content, maxsplit=1, flags=re.I)[0]
    authors, title_field = _reference_fields(head)
    title = re.split(r"\.\s+", title_field, maxsplit=1)[0]
    year = re.search(r"\b(19\d{2}|20\d{2})\b", content)
    location = document.location(start, end)
    return Citation(id=f"cit_{key}", raw_text=raw, doi=extract_doi(content),
                    title=title.strip().rstrip(".") if title and not DOI_REGEX.fullmatch(title.rstrip(".")) else None,
                    authors=[a.strip() for a in authors if a.strip()], year=int(year.group()) if year else None,
                    location=location, location_info=f"{document.file_path} Line {location.line}")


class DocumentParser:
    """The structured API is `parse`; `parse_document` retains the tuple adapter."""

    def parse_document(self, file_path: str):
        parsed = self.parse(file_path)
        citations = {citation.id: citation for citation in parsed.citations}
        pairs = [(citations[claim.citation_id], claim) for claim in parsed.occurrences]
        cited = {claim.citation_id for claim in parsed.occurrences}
        pairs.extend((citation, None) for citation in parsed.citations if citation.id not in cited)
        return pairs

    def parse(self, file_path: str, *, source_bytes: bytes | None = None) -> ParsedDocument:
        if file_path.startswith(("http://", "https://")) or re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", file_path):
            return self._arxiv(file_path)
        document = read_document(file_path, source_bytes=source_bytes)
        suffix = Path(file_path).suffix.lower()
        parsed = ParsedDocument(diagnostics=list(document.diagnostics))
        body = self._strip_math_and_code(document.text)
        if suffix in {".tex", ".bib"}:
            body = re.sub(r"(?m)(?<!\\)%[^\n]*", lambda m: _mask(m.group()), body)
        if suffix == ".bib":
            citations, diagnostics = parse_bibtex(document)
            parsed.diagnostics.extend(diagnostics)
            self._add_references(parsed, citations)
        else:
            if suffix == ".tex":
                body = self._latex_references(document, body, parsed)
                markers = [(match, [k.strip() for k in match.group(1).split(",")]) for match in CITE_COMMAND.finditer(body)]
            else:
                body = self._numbered_references(document, body, parsed)
                markers = []
                for match in NUMBER_MARKER.finditer(body):
                    try:
                        markers.append((match, _number_keys(match.group(1))))
                    except ValueError as exc:
                        parsed.diagnostics.append(ParseDiagnostic(code="INVALID_CITATION_RANGE", message=str(exc), location=document.location(*match.span())))
            bounds = _claim_boundaries(document, body, CITE_COMMAND if suffix == ".tex" else NUMBER_MARKER)
            for match, keys in markers:
                for key in dict.fromkeys(keys):
                    self._add_occurrence(parsed, document, body, match.start(), match.end(), f"cit_{key}", bounds)
            self._inline_dois(document, body, parsed, bounds)
            parsed.occurrences.sort(key=lambda claim: claim.location.char_start)
        if not parsed.citations:
            parsed.diagnostics.append(ParseDiagnostic(code="NO_REFERENCES_PARSED", message="未识别到可核验文献；不代表文档没有引用或已通过审查。"))
        return parsed

    @staticmethod
    def _arxiv(target: str) -> ParsedDocument:
        value = target
        if target.startswith(("http://", "https://")):
            url = urlparse(target)
            match = re.fullmatch(r"/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?/?", url.path)
            if url.hostname not in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"} or not match:
                raise ParserError("Only recognized arXiv URLs or modern arXiv IDs are supported as remote targets")
            value = match.group(1)
        value = re.sub(r"v\d+$", "", value)
        return ParsedDocument(citations=[Citation(id="cit_arxiv_1", raw_text=target,
                              doi=f"10.48550/arxiv.{value}", location_info=f"arXiv Target: {target}")])

    @staticmethod
    def _strip_math_and_code(text: str) -> str:
        patterns = [r"```[\s\S]*?```", r"~~~[\s\S]*?~~~", r"`[^`\n]+`",
                    r"\\begin\{(?:equation|align|math|eqnarray|verbatim|lstlisting)\*?\}[\s\S]*?\\end\{(?:equation|align|math|eqnarray|verbatim|lstlisting)\*?\}",
                    r"\$\$[\s\S]*?\$\$", r"\$(?!\s)[^$\n]+(?<!\s)\$"]
        for pattern in patterns:
            text = re.sub(pattern, lambda match: _mask(match.group()), text)
        return text

    @staticmethod
    def _line_contains_citation(line: str, cite_num: str) -> bool:
        for match in NUMBER_MARKER.finditer(line):
            try:
                if cite_num in _number_keys(match.group(1)):
                    return True
            except ValueError:
                continue
        return False

    @staticmethod
    def _add_references(parsed: ParsedDocument, citations: list[Citation]):
        known = {citation.id: citation for citation in parsed.citations}
        for citation in citations:
            if citation.id in known:
                known[citation.id].parse_status = "AMBIGUOUS"
                parsed.diagnostics.append(ParseDiagnostic(code="DUPLICATE_REFERENCE_KEY", message=f"重复引用键 {citation.id}，未自动选择条目：{citation.raw_text}", location=citation.location))
            else:
                parsed.citations.append(citation)
                known[citation.id] = citation

    def _numbered_references(self, document, body, parsed):
        heading = REFERENCE_HEADING.search(body)
        section_end = len(body)
        if heading:
            following = re.search(r"(?im)^[ \t]*(?:#{1,6}\s+|appendix\b|附录)", body[heading.end():])
            if following:
                section_end = heading.end() + following.start()
            reference_level = next((level for offset, level in document.heading_levels.items()
                                    if heading.start() <= offset < heading.end()), None)
            section_end = min((offset for offset, level in document.heading_levels.items()
                               if heading.end() <= offset < section_end and
                               (reference_level is None or level <= reference_level)), default=section_end)
        # Entries may begin with a textual marker or Word list metadata. Both
        # refer to offsets in the unchanged extracted text.
        entries = {}
        for match in REFERENCE_START.finditer(body):
            if heading:
                if not heading.end() <= match.start() < section_end:
                    continue
            elif not (extract_doi(match.group(3)) or re.search(r"\[[JMDCRNPS]\]", match.group(3), re.I)
                      or re.search(r"\.\s+.+\b(?:19|20)\d{2}\b", match.group(3))):
                continue
            entries[match.start()] = (match.group(1) or match.group(2), match.start(3), match.end())
        if heading:
            for start, number in document.list_numbers.items():
                if not heading.end() <= start < section_end:
                    continue
                literal = entries.get(start)
                if literal and (number is None or literal[0] == str(number)):
                    continue  # An explicit matching label already supplies the content boundary.
                line_end = body.find("\n", start, section_end)
                entries[start] = (str(number) if number is not None else None, start,
                                  section_end if line_end < 0 else line_end)
        starts = sorted(entries)
        for index, start in enumerate(starts):
            key, content_start, line_end = entries[start]
            end = starts[index + 1] if index + 1 < len(starts) else section_end
            if key is None:
                parsed.diagnostics.append(ParseDiagnostic(code="UNSUPPORTED_DOCX_REFERENCE_NUMBERING",
                    message="无法确定此 Word 书目段落的十进制编号；请核对列表格式或提供文字编号。",
                    location=document.location(start, line_end)))
                continue
            tail = body[line_end:end]
            stop = re.search(r"(?m)^\s*(?:#{1,6}\s+|appendix\b|附录)", tail, re.I)
            if not heading:
                stop = re.search(r"\n[ \t]*\n", tail) or stop
            if stop:
                end = line_end + stop.start()
            raw = document.text[start:end].strip()
            content = body[content_start:end].strip()
            self._add_references(parsed, [_reference(key, raw, content, document, start, end)])
            if not heading:
                body = body[:start] + _mask(body[start:end]) + body[end:]
        if heading:
            body = body[:heading.start()] + _mask(body[heading.start():section_end]) + body[section_end:]
            if not entries:
                parsed.diagnostics.append(ParseDiagnostic(code="UNSUPPORTED_REFERENCE_STYLE", message="发现参考文献标题但未识别编号条目；作者年份制等格式尚未支持。", location=document.location(*heading.span())))
        return body

    def _latex_references(self, document, body, parsed):
        items = list(BIBITEM.finditer(body))
        for index, match in enumerate(items):
            end = items[index + 1].start() if index + 1 < len(items) else len(body)
            boundary = re.search(r"\\end\{thebibliography\}", body[match.end():end])
            if boundary:
                end = match.end() + boundary.start()
            self._add_references(parsed, [_reference(match.group(1), document.text[match.start():end].strip(),
                                                    body[match.end():end], document, match.start(), end)])
            body = body[:match.start()] + _mask(body[match.start():end]) + body[end:]
        loaded = set()
        for match in re.finditer(r"\\(?:bibliography|addbibresource)(?:\[[^\]]*\])?\{([^{}]+)\}", body):
            for name in match.group(1).split(","):
                path = Path(document.file_path).parent / name.strip()
                if not path.suffix:
                    path = path.with_suffix(".bib")
                path = path.resolve()
                if path in loaded:
                    continue
                loaded.add(path)
                if not path.is_relative_to(Path(document.file_path).parent) or path.suffix.lower() != ".bib":
                    parsed.diagnostics.append(ParseDiagnostic(code="UNSUPPORTED_BIB_PATH", message=f"只读取原稿目录以内的 .bib 文件：{name}", location=document.location(*match.span())))
                    continue
                try:
                    citations, diagnostics = parse_bibtex(read_document(str(path)))
                    self._add_references(parsed, citations)
                    parsed.diagnostics.extend(diagnostics)
                except (FileNotFoundError, ParserError) as exc:
                    parsed.diagnostics.append(ParseDiagnostic(code="BIB_FILE_UNREADABLE", message=str(exc), location=document.location(*match.span())))
        if re.search(r"\\(?:input|include|newcommand|def)\b", body):
            parsed.diagnostics.append(ParseDiagnostic(code="UNEXPANDED_LATEX", message="检测到 TeX 子文件或宏定义，未执行展开；可能有未提取内容。"))
        definitions = r"\\(?:(?:newcommand|renewcommand|providecommand|DeclareRobustCommand)\*?\s*(?:\{\\\w+\}|\\\w+)\s*(?:\[[^\]]*\]\s*){0,2}|def\s*\\\w+[^{}]*)\{"
        for match in re.finditer(definitions, body):
            end = group_end(body, match.end() - 1)
            end = len(body) if end < 0 else end
            body = body[:match.start()] + _mask(body[match.start():end]) + body[end:]
        return body

    @staticmethod
    def _add_occurrence(parsed, document, body, start, end, citation_id, bounds):
        marker = document.text[start:end]
        if not any(citation.id == citation_id for citation in parsed.citations):
            parsed.citations.append(Citation(id=citation_id, raw_text=marker, parse_status="MISSING"))
            parsed.diagnostics.append(ParseDiagnostic(code="UNRESOLVED_CITATION", message=f"正文标记 {marker} 没有对应参考文献条目。", location=document.location(start, end)))
        boundaries, attached = bounds
        if start in attached:
            left = boundaries[bisect_left(boundaries, attached[start]) - 1]
            right = end
        else:
            left = boundaries[bisect_right(boundaries, start) - 1]
            right = boundaries[bisect_left(boundaries, end)]
        fragment = body[left:right]
        left += len(fragment) - len(fragment.lstrip())
        right -= len(fragment) - len(fragment.rstrip())
        sentence = document.text[left:right].strip()
        parsed.occurrences.append(ContextClaim(citation_id=citation_id,
            occurrence_id=f"occ_{len(parsed.occurrences) + 1}", marker=marker,
            claim_sentence=sentence, surrounding_context=sentence,
            location=document.location(start, end)))

    def _inline_dois(self, document, body, parsed, bounds):
        for match in DOI_REGEX.finditer(body):
            doi = clean_doi(match.group())
            candidates = [citation for citation in parsed.citations if (citation.doi or "").lower() == doi.lower()]
            if len(candidates) == 1:
                citation = candidates[0]
            else:
                number = len(parsed.citations) + 1
                ids = {citation.id for citation in parsed.citations}
                while f"cit_doi_{number}" in ids:
                    number += 1
                citation = Citation(id=f"cit_doi_{number}", raw_text=doi, doi=doi,
                                    location=document.location(match.start(), match.start() + len(doi)))
                parsed.citations.append(citation)
            self._add_occurrence(parsed, document, body, match.start(), match.start() + len(doi), citation.id, bounds)
