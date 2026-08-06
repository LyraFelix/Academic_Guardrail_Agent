"""Reference Candidate Resolver & Re-ranker (Retrieve Top-K -> Re-rank -> Accept)."""

import re
import difflib
from typing import List, Dict, Any, Optional
from academic_guardrail.core.models import Citation


class ReferenceResolver:
    """Evaluates and re-ranks retrieved paper candidates against target citation."""

    def _calc_similarity(self, s1: str, s2: str) -> float:
        if not s1 or not s2:
            return 0.0
        return difflib.SequenceMatcher(None, s1.lower().strip(), s2.lower().strip()).ratio()

    def _extract_author_tokens(self, text_or_list: Any) -> set:
        tokens = set()
        stop_words = {"and", "et", "al", "d", "c", "p", "a", "b", "e", "f", "g", "h", "j", "k", "l", "m", "n", "o", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z"}
        if isinstance(text_or_list, list):
            for item in text_or_list:
                if isinstance(item, str):
                    words = re.findall(r'\b[a-zA-Z\u4e00-\u9fa5]{2,}\b', item.lower())
                    tokens.update([w for w in words if w not in stop_words])
                elif isinstance(item, dict):
                    name = item.get("display_name") or item.get("author", {}).get("display_name") or ""
                    if name:
                        words = re.findall(r'\b[a-zA-Z\u4e00-\u9fa5]{2,}\b', name.lower())
                        tokens.update([w for w in words if w not in stop_words])
        elif isinstance(text_or_list, str):
            words = re.findall(r'\b[a-zA-Z\u4e00-\u9fa5]{2,}\b', text_or_list.lower())
            tokens.update([w for w in words if w not in stop_words])
        return tokens

    def compute_candidate_score(self, cit: Citation, candidate: Dict[str, Any]) -> float:
        c_title = (cit.title or "").strip()
        cand_title = (candidate.get("title") or "").strip()

        if not c_title or not cand_title:
            return 0.0

        # 1. Title Similarity (0.30)
        title_sim = self._calc_similarity(c_title, cand_title)
        c_clean = re.sub(r'[^\w\s]', '', c_title.lower()).strip()
        cand_clean = re.sub(r'[^\w\s]', '', cand_title.lower()).strip()
        if len(c_clean) >= 4 and (c_clean in cand_clean or cand_clean in c_clean):
            title_sim = max(title_sim, 0.85)

        # 2. Author Token Match (0.35)
        c_tokens = self._extract_author_tokens(cit.authors or cit.raw_text)
        cand_tokens = self._extract_author_tokens(candidate.get("authors") or candidate.get("author") or [])
        author_match = 0.0
        if c_tokens and cand_tokens:
            overlap = c_tokens.intersection(cand_tokens)
            if overlap:
                author_match = min(1.0, len(overlap) / float(max(1, min(len(c_tokens), len(cand_tokens)))))

        # 3. Year Match (0.20)
        c_year = cit.year
        if not c_year:
            ym = re.search(r'\b(19\d{2}|20\d{2})\b', cit.raw_text)
            c_year = int(ym.group(1)) if ym else None

        cand_year = candidate.get("publication_year") or candidate.get("year")
        year_match = 0.0
        if c_year and cand_year:
            try:
                cand_year_int = int(cand_year)
                diff = abs(c_year - cand_year_int)
                if diff == 0:
                    year_match = 1.0
                elif diff == 1:
                    year_match = 0.5
            except Exception:
                pass
        else:
            year_match = 0.5

        # 4. Venue / Publisher Match (0.15)
        venue_match = 0.5
        cand_venue = candidate.get("publisher") or candidate.get("journal") or candidate.get("venue") or ""
        if cand_venue and cit.raw_text:
            if cand_venue.lower() in cit.raw_text.lower():
                venue_match = 1.0

        score = (
            0.35 * author_match +
            0.30 * title_sim +
            0.20 * year_match +
            0.15 * venue_match
        )
        return round(score, 2)

    def select_best_candidate(self, cit: Citation, candidates: List[Dict[str, Any]], min_score: float = 0.40) -> Optional[Dict[str, Any]]:
        if not candidates:
            return None

        scored_candidates = []
        for cand in candidates:
            if not isinstance(cand, dict):
                continue
            s = self.compute_candidate_score(cit, cand)
            scored_candidates.append((s, cand))

        if not scored_candidates:
            return None

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_cand = scored_candidates[0]

        if best_score >= min_score:
            best_cand["match_score"] = best_score
            return best_cand

        return None
