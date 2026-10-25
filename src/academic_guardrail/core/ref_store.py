"""Local Reference Store: Scans local folder of reference papers (PDF, DOCX, TXT), extracts PaperRecord metadata & abstracts for content-level claim alignment."""

import os
import re
from typing import Optional, Dict, Tuple, List
from academic_guardrail.core.models import Citation, PaperRecord
from academic_guardrail.core.ref_resolver import ReferenceResolver

try:
    import docx
except ImportError:
    docx = None


class LocalRefStore:
    """Scans a directory containing reference PDFs, DOCXs, or TXTs, extracts structured PaperRecord instances, and matches by content."""

    def __init__(self, refs_dir: Optional[str] = None):
        self.refs_dir = refs_dir
        self.records: List[PaperRecord] = []
        self.resolver = ReferenceResolver()
        if refs_dir and os.path.exists(refs_dir):
            self._scan_directory(refs_dir)

    def _scan_directory(self, refs_dir: str):
        for root, _, files in os.walk(refs_dir):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext not in ['.txt', '.md', '.docx', '.pdf']:
                    continue
                file_path = os.path.join(root, f)
                record = self._extract_paper_record(file_path, f, ext)
                if record and (record.title or record.fulltext):
                    self.records.append(record)

    def _extract_paper_record(self, path: str, filename: str, ext: str) -> Optional[PaperRecord]:
        fulltext = ""
        try:
            if ext in ['.txt', '.md']:
                with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
                    fulltext = fp.read()
            elif ext == '.docx' and docx:
                doc = docx.Document(path)
                fulltext = "\n".join([p.text for p in doc.paragraphs if p.text])
            elif ext == '.pdf':
                from academic_guardrail.core.pdf_extractor import PDFTextExtractor
                try:
                    fulltext = PDFTextExtractor.extract(path)
                except Exception:
                    return None
        except Exception:
            return None

        if not fulltext or not fulltext.strip():
            return None

        # Extract Title: First non-empty paragraph or header line
        lines = [line.strip() for line in fulltext.split('\n')
                 if line.strip() and not re.fullmatch(r'--- Page \d+ ---', line.strip())]
        title = lines[0] if lines else filename
        if len(title) > 200:
            title = title[:200]

        # Extract Abstract: Search for "Abstract" / "摘要" section
        abstract = ""
        abs_match = re.search(r'(abstract|摘要)[:\s]+(.*?)(?=\n\n|\n[1-9]|introduction|引言|$)', fulltext, re.IGNORECASE | re.DOTALL)
        if abs_match:
            abstract = abs_match.group(2).strip()[:1000]
        else:
            # Fallback to first 500 characters if no Abstract keyword
            abstract = fulltext[:500].strip()

        # Extract Year
        year = None
        ym = re.search(r'\b(19\d{2}|20\d{2})\b', fulltext[:1500])
        if ym:
            year = int(ym.group(1))

        # Extract Authors (words before title/abstract or lines)
        authors = []
        if len(lines) > 1:
            authors_str = lines[1]
            if len(authors_str) < 100 and not any(kw in authors_str.lower() for kw in ["abstract", "摘要", "university", "大学"]):
                authors = [a.strip() for a in re.split(r'[,;]\s*', authors_str) if a.strip()]

        return PaperRecord(
            filename=filename,
            filepath=path,
            title=title,
            authors=authors,
            year=year,
            abstract=abstract,
            fulltext=fulltext
        )

    def find_match(self, citation: Citation) -> Optional[Dict]:
        """Match record metadata only. A bibliography mention is not identity evidence."""
        candidates = [record.model_dump() for record in self.records]
        # Identical extracted metadata does not mean identical file contents.
        best = self.resolver.select_best_candidate(citation, candidates, deduplicate=False)
        if not best or best.get("is_uncertain") or best.get("match_confidence") == "UNCERTAIN":
            return None
        return best

    def find_abstract_for_citation(self, title: str, raw_text: str) -> Optional[Tuple[str, str, float]]:
        """Compatibility wrapper; new callers should pass full metadata to find_match."""
        match = self.find_match(Citation(id="local", title=title or raw_text, raw_text=raw_text))
        if not match:
            return None
        text = match.get("abstract") or match.get("fulltext") or ""
        return text.strip(), match["filename"], match["match_score"]
