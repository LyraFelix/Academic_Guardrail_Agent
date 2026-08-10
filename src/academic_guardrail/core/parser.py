"""Document parser module supporting PDF, DOCX, Markdown, LaTeX, and BibTeX."""

import os
import re
from typing import List, Tuple
from academic_guardrail.core.models import Citation, ContextClaim
from academic_guardrail.core.exceptions import ParserError

DOI_REGEX = re.compile(r'10\.\d{4,9}/[-._;()/:A-Za-z0-9]+')
# Characters that must be stripped from the right end of a raw DOI match
# to avoid sending trailing sentence punctuation to external APIs.
_DOI_TRAIL_CHARS = ".,;:!?)]}>"
GBT7714_HEAD_REGEX = re.compile(r'^\[(\d+)\]\s*(.+)')


class DocumentParser:
    """Parses various document formats into structured Citations and ContextClaims."""

    def parse_document(self, file_path: str) -> List[Tuple[Citation, ContextClaim]]:
        # Handle arXiv URL or arXiv ID directly
        if file_path.startswith("http://") or file_path.startswith("https://") or "arxiv.org" in file_path or re.match(r'^\d{4}\.\d{4,5}(v\d+)?$', file_path):
            return self._parse_arxiv_target(file_path)

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.md', '.txt']:
            return self._parse_text_file(file_path)
        elif ext == '.docx':
            return self._parse_docx_file(file_path)
        elif ext == '.pdf':
            return self._parse_pdf_file(file_path)
        elif ext in ['.tex', '.bib']:
            return self._parse_latex_bib_file(file_path)
        else:
            return self._parse_text_file(file_path)

    def _parse_arxiv_target(self, target: str) -> List[Tuple[Citation, ContextClaim]]:
        arxiv_match = re.search(r'(\d{4}\.\d{4,5})', target)
        arxiv_id = arxiv_match.group(1) if arxiv_match else target
        doi = f"10.48550/arxiv.{arxiv_id}"
        
        citation = Citation(
            id="cit_arxiv_1",
            raw_text=f"arXiv:{arxiv_id}",
            doi=doi,
            title=f"arXiv Preprint {arxiv_id}",
            authors=[],
            year=None,
            location_info=f"arXiv Target: {target}"
        )
        claim = ContextClaim(
            claim_sentence=f"arXiv paper {arxiv_id}",
            citation_id="cit_arxiv_1",
            surrounding_context=f"arXiv Target: {target}"
        )
        return [(citation, claim)]

    @staticmethod
    def _strip_math_and_code(text: str) -> str:
        """Strips code blocks, inline code, and LaTeX math blocks/inline math to prevent false matches."""
        # 1. Code blocks ```...```
        t = re.sub(r'```[\s\S]*?```', '', text)
        # 2. Inline code `...`
        t = re.sub(r'`[^`\n]+`', '', t)
        # 3. LaTeX environments \begin{equation}...\end{equation} or \begin{align}...\end{align}
        t = re.sub(r'\\begin\{(?:equation|align|math|eqnarray)\*?\}[\s\S]*?\\end\{(?:equation|align|math|eqnarray)\*?\}', '', t)
        # 4. Display math $$...$$
        t = re.sub(r'\$\$[\s\S]*?\$\$', '', t)
        # 5. Inline math $...$ (avoiding dollar signs with numbers like $100)
        t = re.sub(r'\$(?!\s)[^\$\n]+(?<!\s)\$', '', t)
        return t

    @staticmethod
    def _line_contains_citation(line: str, cite_num: str) -> bool:
        """Checks if line contains citation bracket matching cite_num, supporting range expansion like [1, 3-5]."""
        if not cite_num.isdigit():
            return re.search(r'\[\s*' + re.escape(cite_num) + r'\s*\]', line) is not None

        target_num = int(cite_num)
        for match in re.finditer(r'\[\s*([\d\s,,\-\–\—]+)\s*\]', line):
            content = match.group(1)
            for part in content.split(','):
                part = part.strip()
                if '-' in part or '–' in part or '—' in part:
                    range_parts = re.split(r'[\-\–\—]', part)
                    if len(range_parts) == 2 and range_parts[0].strip().isdigit() and range_parts[1].strip().isdigit():
                        start, end = int(range_parts[0].strip()), int(range_parts[1].strip())
                        if start <= target_num <= end:
                            return True
                elif part.isdigit() and int(part) == target_num:
                    return True
        return False

    def _extract_citations_and_claims_from_text(self, text: str, location_prefix: str = "") -> List[Tuple[Citation, ContextClaim]]:
        pairs: List[Tuple[Citation, ContextClaim]] = []
        clean_text = self._strip_math_and_code(text)
        lines = clean_text.split('\n')
        
        # 1. Parse Reference Section / Inline Citations
        for i, line in enumerate(lines):
            line_str = line.strip()
            if not line_str:
                continue

            gbt_match = GBT7714_HEAD_REGEX.match(line_str)
            if gbt_match:
                cite_num, content = gbt_match.groups()
                
                # Check for Journal Type Tag [J], [M], [D], [C]
                type_match = re.search(r'\[([JMDCRNPS])\]', content, re.IGNORECASE)
                doc_type = type_match.group(1).upper() if type_match else "J"
                
                # Split Title and Authors
                parts = content.split(f"[{type_match.group(1)}]" if type_match else ".")
                head_part = parts[0] if parts else content
                
                authors_title = head_part.split('.', 1)
                authors_str = authors_title[0].strip() if len(authors_title) > 1 else ""
                title_str = authors_title[1].strip() if len(authors_title) > 1 else authors_title[0].strip()
                
                # Year Match
                year_match = re.search(r'\b(19\d{2}|20\d{2})\b', content)
                year = int(year_match.group(1)) if year_match else None
                
                # DOI Match — strip trailing punctuation to prevent 404s
                doi_match = DOI_REGEX.search(line_str)
                doi = doi_match.group(0).rstrip(_DOI_TRAIL_CHARS) if doi_match else None

                citation = Citation(
                    id=f"cit_{cite_num}",
                    raw_text=line_str,
                    doi=doi,
                    title=title_str if title_str else line_str,
                    authors=[a.strip() for a in authors_str.split(',') if a.strip()],
                    year=year,
                    location_info=f"{location_prefix} Line {i+1}"
                )

                # Search inline text for Context Claim referring to [cite_num]
                claim_sentence = ""
                context = ""
                for ctx_line in lines:
                    if ctx_line != line_str and self._line_contains_citation(ctx_line, cite_num):
                        claim_sentence = ctx_line.strip()
                        context = ctx_line.strip()
                        break
                
                if not claim_sentence:
                    claim_sentence = f"正文中引用了文献 [{cite_num}]。"
                    context = line_str

                claim = ContextClaim(
                    citation_id=citation.id,
                    claim_sentence=claim_sentence,
                    surrounding_context=context
                )
                pairs.append((citation, claim))
                continue

            # 2. Standalone DOI Match — strip trailing punctuation to prevent 404s
            doi_match = DOI_REGEX.search(line_str)
            if doi_match and ("http" in line_str or "doi" in line_str.lower()):
                doi = doi_match.group(0).rstrip(_DOI_TRAIL_CHARS)
                cid = f"cit_doi_{len(pairs)+1}"
                citation = Citation(
                    id=cid,
                    raw_text=line_str,
                    doi=doi,
                    title=line_str[:60],
                    location_info=f"{location_prefix} Line {i+1}"
                )
                claim = ContextClaim(
                    citation_id=cid,
                    claim_sentence=line_str,
                    surrounding_context=line_str
                )
                pairs.append((citation, claim))

        return pairs

    def _parse_text_file(self, file_path: str) -> List[Tuple[Citation, ContextClaim]]:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        return self._extract_citations_and_claims_from_text(content, location_prefix="Text")

    def _parse_docx_file(self, file_path: str) -> List[Tuple[Citation, ContextClaim]]:
        try:
            import docx
            doc = docx.Document(file_path)
            full_text = []
            for p in doc.paragraphs:
                if p.text.strip():
                    full_text.append(p.text.strip())
            text = "\n".join(full_text)
            return self._extract_citations_and_claims_from_text(text, location_prefix="DOCX")
        except ImportError:
            return self._parse_text_file(file_path)
        except Exception as e:
            raise ParserError(f"Failed to parse DOCX file {file_path}: {e}") from e

    def _parse_pdf_file(self, file_path: str) -> List[Tuple[Citation, ContextClaim]]:
        full_text = []
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                for idx, page in enumerate(pdf.pages):
                    p_text = page.extract_text()
                    if p_text:
                        full_text.append(f"--- Page {idx+1} ---\n" + p_text)
            text = "\n".join(full_text)
            return self._extract_citations_and_claims_from_text(text, location_prefix="PDF")
        except ImportError:
            return self._parse_text_file(file_path)
        except Exception as e:
            raise ParserError(f"Failed to parse PDF file {file_path}: {e}") from e

    def _parse_latex_bib_file(self, file_path: str) -> List[Tuple[Citation, ContextClaim]]:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        return self._extract_citations_and_claims_from_text(content, location_prefix="LaTeX/BibTeX")
