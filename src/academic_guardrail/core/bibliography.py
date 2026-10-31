"""A small literal BibTeX reader: balanced fields, no macro evaluation or TeX execution."""

import re

from academic_guardrail.core.identifiers import extract_doi
from academic_guardrail.core.models import Citation, ParseDiagnostic
from academic_guardrail.core.text_extraction import ExtractedText


def _split_top_level(text: str, separator: str = ",") -> list[str]:
    parts, start, depth, quoted, escaped = [], 0, 0, False, False
    for pos, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
        elif char == '"' and depth == 0:
            quoted = not quoted
        elif not quoted:
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            elif char == separator and depth == 0:
                parts.append(text[start:pos])
                start = pos + 1
    parts.append(text[start:])
    return parts


def group_end(text: str, start: int) -> int:
    """Find the end of a balanced brace/parenthesis group, respecting quotes."""
    opening = text[start]
    closing = "}" if opening == "{" else ")"
    braces, quoted, escaped = 0, False, False
    for pos in range(start + 1, len(text)):
        char = text[pos]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
        elif char == '"' and braces == 0:
            quoted = not quoted
        elif not quoted:
            if char == "{":
                braces += 1
            elif char == "}" and braces:
                braces -= 1
            elif char == closing and braces == 0:
                return pos + 1
    return -1


def literal_text(value: str) -> str:
    """Remove grouping braces and common formatting wrappers, not arbitrary macros."""
    value = re.sub(r"\\(?:textit|textbf|emph|textrm)\s*", "", value)
    value = re.sub(r"\\([&_%#$])", r"\1", value)
    return " ".join(value.replace("{", "").replace("}", "").split())


def _authors(value: str) -> list[str]:
    # `and` inside a protected organization name is ordinary text.
    authors, start, depth = [], 0, 0
    for token in re.finditer(r"\\.|[{}]|\s+and\s+", value):
        if token.group() == "{":
            depth += 1
        elif token.group() == "}":
            depth -= 1
        elif token.group().strip() == "and" and depth == 0:
            authors.append(literal_text(value[start:token.start()]))
            start = token.end()
    authors.append(literal_text(value[start:]))
    return [author for author in authors if author]


def parse_bibtex(document: ExtractedText) -> tuple[list[Citation], list[ParseDiagnostic]]:
    citations, diagnostics = [], []
    # Preserve offsets while removing whole-line BibTeX comments.
    text = re.sub(r"(?m)^\s*%[^\n]*", lambda m: re.sub(r"[^\n]", " ", m.group()), document.text)
    cursor = 0
    for entry in re.finditer(r"@([A-Za-z]+)\s*([({])", text):
        if entry.start() < cursor:
            continue
        end = group_end(text, entry.end() - 1)
        if end < 0:
            diagnostics.append(ParseDiagnostic(code="MALFORMED_BIBTEX", message="BibTeX 条目缺少配对括号，未猜测其内容。", location=document.location(entry.start(), len(text))))
            break
        cursor = end
        location = document.location(entry.start(), end)
        if entry.group(1).lower() in {"comment", "preamble", "string"}:
            if entry.group(1).lower() != "comment":
                diagnostics.append(ParseDiagnostic(code="UNSUPPORTED_BIBTEX_MACRO", message="不执行 BibTeX string/preamble 宏。", location=location))
            continue
        pieces = _split_top_level(text[entry.end():end - 1])
        key = pieces[0].strip()
        if not key or "=" in key:
            diagnostics.append(ParseDiagnostic(code="MALFORMED_BIBTEX", message="BibTeX 条目缺少引用键。", location=location))
            continue
        fields, raw_authors = {}, ""
        for piece in pieces[1:]:
            if not piece.strip():
                continue
            name, equal, value = piece.partition("=")
            name, value = name.strip().lower(), value.strip()
            supported = equal and len(_split_top_level(value, "#")) == 1
            if supported and ((value.startswith("{") and value.endswith("}")) or
                              (value.startswith('"') and value.endswith('"'))):
                cleaned = literal_text(value[1:-1])
                if re.search(r"\\[A-Za-z]+", cleaned):
                    diagnostics.append(ParseDiagnostic(code="UNSUPPORTED_BIBTEX_MACRO", message=f"条目 {key} 的 {name} 包含未展开的 TeX 命令，未采用该字段。", location=location))
                    continue
                fields[name] = cleaned
                if name == "author":
                    raw_authors = value[1:-1]
            elif supported and value.isdigit():
                fields[name] = value
            else:
                diagnostics.append(ParseDiagnostic(code="UNSUPPORTED_BIBTEX_VALUE", message=f"条目 {key} 的 {name or '未知字段'} 使用了宏、拼接或无法解析的值，未采用该字段。", location=location))
        year = fields.get("year", "")
        citations.append(Citation(
            id=f"cit_{key}", raw_text=document.text[entry.start():end],
            title=fields.get("title"), doi=extract_doi(fields.get("doi", "") or fields.get("url", "")),
            authors=_authors(raw_authors),
            year=int(year) if year.isdigit() and len(year) == 4 else None,
            venue=fields.get("journal") or fields.get("booktitle"), location=location,
            location_info=f"{document.file_path} Line {location.line}"))
    return citations, diagnostics
