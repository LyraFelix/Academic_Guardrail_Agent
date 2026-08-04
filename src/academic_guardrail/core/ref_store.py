"""Local Reference Store: Scans local folder of reference papers (PDF, DOCX, TXT) and extracts abstracts for claim alignment."""

import os
import re
import difflib
from typing import Optional, Dict, Tuple

try:
    import docx
except ImportError:
    docx = None

try:
    import pypdf
except ImportError:
    pypdf = None


class LocalRefStore:
    """Scans a directory containing reference PDFs, DOCXs, or TXTs, and indexes their titles & abstracts."""

    def __init__(self, refs_dir: Optional[str] = None):
        self.refs_dir = refs_dir
        self.papers: Dict[str, str] = {}  # filename/title_key -> full_text_or_abstract
        if refs_dir and os.path.exists(refs_dir):
            self._scan_directory(refs_dir)

    def _scan_directory(self, refs_dir: str):
        for root, _, files in os.walk(refs_dir):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                file_path = os.path.join(root, f)
                text = self._extract_text(file_path, ext)
                if text:
                    self.papers[f] = text

    def _extract_text(self, path: str, ext: str) -> str:
        try:
            if ext in ['.txt', '.md']:
                with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
                    return fp.read()
            elif ext == '.docx' and docx:
                doc = docx.Document(path)
                return "\n".join([p.text for p in doc.paragraphs if p.text])
            elif ext == '.pdf' and pypdf:
                reader = pypdf.PdfReader(path)
                pages = [p.extract_text() for p in reader.pages[:3] if p.extract_text()]
                return "\n".join(pages)
        except Exception:
            pass
        return ""

    def find_abstract_for_citation(self, title: str, raw_text: str) -> Optional[Tuple[str, str]]:
        """Finds matching local paper text by title/raw_text similarity.
        Returns (abstract_or_text, source_filename) or None.
        """
        if not self.papers:
            return None

        search_key = title if title else raw_text
        clean_key = re.sub(r'[^\w]', '', search_key.lower())

        best_match_file = None
        best_sim = 0.0

        for filename, text in self.papers.items():
            clean_fn = re.sub(r'[^\w]', '', filename.lower())
            sim = difflib.SequenceMatcher(None, clean_key, clean_fn).ratio()

            # Also check if title keywords appear inside the paper text
            if len(clean_key) > 5 and clean_key[:10] in clean_fn:
                sim = max(sim, 0.85)

            if sim > best_sim:
                best_sim = sim
                best_match_file = filename

        if best_sim >= 0.40 and best_match_file:
            full_text = self.papers[best_match_file]
            # Try extracting abstract block
            abs_match = re.search(r'(?:摘要|Abstract)[\s\:\：]+([\s\S]{50,600})', full_text, re.IGNORECASE)
            if abs_match:
                return abs_match.group(1).strip(), best_match_file
            else:
                # Return first 500 characters
                return full_text[:500].strip(), best_match_file

        return None
