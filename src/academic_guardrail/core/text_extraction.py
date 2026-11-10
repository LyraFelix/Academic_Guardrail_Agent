"""Read text in document order and preserve coordinates independently of parsing."""

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from academic_guardrail.core.exceptions import ParserError
from academic_guardrail.core.models import ParseDiagnostic, SourceLocation


@dataclass
class ExtractedText:
    file_path: str
    text: str
    page_starts: list[int] = field(default_factory=list)
    diagnostics: list[ParseDiagnostic] = field(default_factory=list)

    def location(self, start: int, end: int) -> SourceLocation:
        page = None
        if self.page_starts:
            page = sum(offset <= start for offset in self.page_starts)
        return SourceLocation(file_path=self.file_path, page=page,
                              line=self.text.count("\n", 0, start) + 1,
                              char_start=start, char_end=end)


def _docx_text(path: Path, source_bytes: bytes | None = None) -> tuple[str, bool]:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(BytesIO(source_bytes) if source_bytes is not None else str(path))
    lines = []

    def read_elements(elements, parent):
        for element in elements:
            if element.tag.endswith("}p"):
                lines.append(Paragraph(element, parent).text)
            elif element.tag.endswith("}tbl"):
                table = Table(element, parent)
                # Merged cells share XML nodes; read each physical cell once.
                seen = set()
                for row in table.rows:
                    for cell in row.cells:
                        if cell._tc not in seen:
                            seen.add(cell._tc)
                            read_elements(cell._tc, cell)

    read_elements(doc.element.body, doc)
    unsupported = bool(doc.element.xpath(".//w:footnoteReference | .//w:endnoteReference | .//w:txbxContent"))
    return "\n".join(lines), unsupported


def read_document(file_path: str, *, source_bytes: bytes | None = None) -> ExtractedText:
    """Parse supplied bytes without reopening the path, retaining its coordinates.

    PDF pages use two-newline separators; other formats have no page claims.
    The optional bytes let callers hash the exact input that is parsed.
    """
    path = Path(file_path).resolve()
    if source_bytes is None and not path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")
    try:
        raw_bytes = path.read_bytes() if source_bytes is None else source_bytes
        if path.suffix.lower() == ".pdf":
            from academic_guardrail.core.pdf_extractor import PDFTextExtractor
            pages = PDFTextExtractor.extract_pages(str(path), source_bytes=raw_bytes)
            document = ExtractedText(str(path), "\n\n".join(pages))
            offset = 0
            for number, text in enumerate(pages, 1):
                document.page_starts.append(offset)
                if not text.strip():
                    document.diagnostics.append(ParseDiagnostic(
                        code="EMPTY_PDF_PAGE", message=f"PDF 第 {number} 页无可提取文本；未执行 OCR。",
                        location=SourceLocation(file_path=str(path), page=number,
                                                char_start=offset, char_end=offset + len(text))))
                offset += len(text) + 2
            return document
        if path.suffix.lower() == ".docx":
            text, unsupported = _docx_text(path, raw_bytes)
            document = ExtractedText(str(path), text)
            if unsupported:
                document.diagnostics.append(ParseDiagnostic(
                    code="UNSUPPORTED_DOCX_CONTENT", message="检测到脚注、尾注或文本框；当前仅读取正文段落和表格。"))
            return document
        # Match the universal-newline behavior of the legacy text-mode reader.
        text = raw_bytes.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        return ExtractedText(str(path), text)
    except (OSError, UnicodeError, ImportError, RuntimeError) as exc:
        raise ParserError(f"Cannot extract {path.name}: {exc}") from exc
    except Exception as exc:
        # Format-library errors have different types; expose a single boundary.
        raise ParserError(f"Failed to parse {path.name}: {exc}") from exc
