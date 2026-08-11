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
    def extract(file_path: str) -> str:
        """Extracts full text from a PDF file, page-by-page.

        Returns the concatenated text string, or raises RuntimeError if
        pypdf is not installed.

        Args:
            file_path: Absolute or relative path to the PDF file.

        Returns:
            Multi-page text as a single string with page separators.

        Raises:
            RuntimeError: If pypdf is not installed.
            Exception: Propagated from pypdf on parse failure.
        """
        if not _HAS_PYPDF:
            raise RuntimeError(
                "pypdf is required for PDF parsing. "
                "Install it with: pip install pypdf"
            )
        pages: List[str] = []
        reader = pypdf.PdfReader(file_path)
        for idx, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                pages.append(f"--- Page {idx + 1} ---\n" + page_text)
        return "\n".join(pages)
