"""Unified PDF text extraction utility using pypdf.

Single source-of-truth for PDF reading across all modules.
Both the document parser and the local reference store use this extractor
to avoid maintaining two separate PDF dependencies.
"""

import logging
from typing import List

logger = logging.getLogger(__name__)

try:
    import pypdf
    _HAS_PYPDF = True
except ImportError:
    _HAS_PYPDF = False
    logger.warning(
        "[academic_guardrail] pypdf is not installed. PDF parsing will be unavailable. "
        "Run: pip install pypdf"
    )


class PDFTextExtractor:
    """Extracts plain text from PDF files using pypdf.

    Usage::

        text = PDFTextExtractor.extract(path)
        if text is None:
            # pypdf not installed or file unreadable
            ...
    """

    @staticmethod
    def extract_pages(file_path: str) -> List[str]:
        """Keep every physical page, including pages with no extractable text."""
        if not _HAS_PYPDF:
            raise RuntimeError(
                "pypdf is required for PDF parsing. "
                "Install it with: pip install pypdf"
            )
        reader = pypdf.PdfReader(file_path)
        return [page.extract_text() or "" for page in reader.pages]

    @staticmethod
    def extract(file_path: str) -> str:
        """Compatibility view. Page labels must never pollute paper metadata."""
        return "\n\n".join(PDFTextExtractor.extract_pages(file_path))
