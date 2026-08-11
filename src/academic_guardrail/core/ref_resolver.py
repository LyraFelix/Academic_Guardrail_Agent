"""Reference Candidate Resolver & Re-ranker with Multi-Stage Entity Resolution."""

import re
import difflib
from typing import List, Dict, Any, Optional, Tuple
from academic_guardrail.core.models import Citation
from academic_guardrail.core.config import GuardrailConfig

STOP_WORDS = {
    "the", "a", "an", "of", "on", "in", "for", "with", "by", "about", "against",
    "between", "into", "through", "during", "before", "after", "above", "below",
    "to", "from", "up", "down", "in", "out", "over", "under", "again", "further",
    "then", "once", "and", "or", "study", "research", "analysis", "approach", "paper"
}


class ReferenceResolver:
    """Evaluates and re-ranks retrieved paper candidates against target citation."""

    def _clean_tokens(self, text: str) -> List[str]:
        if not text:
            return []
        words = re.findall(r'\b[a-zA-Z\u4e00-\u9fa5]{2,}\b', text.lower())
        return [w for w in words if w not in STOP_WORDS]

    def _calc_hybrid_title_sim(self, c_title: str, cand_title: str) -> float:
        if not c_title or not cand_title:
            return 0.0
        seq_sim = difflib.SequenceMatcher(None, c_title.lower().strip(), cand_title.lower().strip()).ratio()

        c_tokens = set(self._clean_tokens(c_title))
        cand_tokens = set(self._clean_tokens(cand_title))

        if not c_tokens or not cand_tokens:
            token_sim = seq_sim
        else:
            intersection = c_tokens.intersection(cand_tokens)
            union = c_tokens.union(cand_tokens)
            token_sim = len(intersection) / float(len(union))

        return round(0.6 * seq_sim + 0.4 * token_sim, 3)

    def _calc_author_score(self, cit: Citation, candidate: Dict[str, Any]) -> float:
        c_authors = self._clean_tokens(" ".join(cit.authors) if isinstance(cit.authors, list) else (cit.raw_text or ""))
        cand_authors_raw = candidate.get("authors") or candidate.get("author") or []
        cand_authors = self._clean_tokens(" ".join(cand_authors_raw) if isinstance(cand_authors_raw, list) else str(cand_authors_raw))

        if not c_authors or not cand_authors:
            return 0.0

        # First author match (70% weight)
        first_c = c_authors[0]
        first_match = 0.0
        if first_c in cand_authors:
            first_match = 1.0 if len(first_c) > 3 else 0.7

        # Co-author overlap (30% weight)
        c_set = set(c_authors)
        cand_set = set(cand_authors)
        co_overlap = len(c_set.intersection(cand_set)) / float(max(1, len(c_set)))

        return round(0.7 * first_match + 0.3 * co_overlap, 3)

    def compute_candidate_score(self, cit: Citation, candidate: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        c_title = (cit.title or "").strip()
        cand_title = (candidate.get("title") or "").strip()

        # Stage 0: Reliability Check
        title_tokens = self._clean_tokens(c_title)
        is_title_reliable = (len(c_title) >= 12 and len(title_tokens) >= 3)

        # Stage 1: Title Hard Floor (Only when reliable)
        title_sim = self._calc_hybrid_title_sim(c_title, cand_title)
        if is_title_reliable and title_sim < GuardrailConfig.REFERENCE_TITLE_HARD_FLOOR:
            return 0.0, {"status": "REJECTED_HARD_FLOOR"}

        # Stage 2: Identity Gate
        author_score = self._calc_author_score(cit, candidate)
        c_year = cit.year or (int(re.search(r'\b(19\d{2}|20\d{2})\b', cit.raw_text).group(1)) if re.search(r'\b(19\d{2}|20\d{2})\b', cit.raw_text or "") else None)
        cand_year = candidate.get("publication_year") or candidate.get("year")

        year_match = None
        if c_year and cand_year:
            try:
                diff = abs(int(c_year) - int(cand_year))
                year_match = 1.0 if diff == 0 else (0.5 if diff == 1 else 0.0)
            except Exception:
                pass

        has_anchor_a = (title_sim >= 0.70)
        has_anchor_b = (author_score >= 0.50 and title_sim >= 0.40)
        has_anchor_c = (author_score >= 0.50 and (year_match is not None and year_match >= 0.5) and title_sim >= 0.35)

        if not (has_anchor_a or has_anchor_b or has_anchor_c):
            return 0.0, {"status": "REJECTED_IDENTITY_GATE"}

        # Stage 3: Dynamic Normalization Weighted Score
        weights = {"title": 0.45, "author": 0.30, "year": 0.15, "venue": 0.10}
        scores = {"title": title_sim}

        if author_score > 0:
            scores["author"] = author_score

        if year_match is not None:
            scores["year"] = year_match

        cand_venue = (candidate.get("publisher") or candidate.get("journal") or candidate.get("venue") or "").lower()
        if cand_venue and cit.raw_text and len(cit.raw_text) > 20:
            scores["venue"] = 1.0 if cand_venue in cit.raw_text.lower() else 0.0

        active_weight = sum(weights[k] for k in scores.keys())
        weighted_sum = sum(weights[k] * scores[k] for k in scores.keys())
        final_score = round(weighted_sum / active_weight, 3)

        meta = {
            "status": "ELIGIBLE",
            "score": final_score,
            "title_score": round(title_sim, 3),
            "author_score": round(author_score, 3),
            "year_score": year_match,
            "venue_score": scores.get("venue", 0.0)
        }

        return final_score, meta

    @staticmethod
    def normalize_doi(doi: Optional[str]) -> Optional[str]:
        """Normalizes raw DOI strings into canonical lowercase format without URL prefixes."""
        if not doi:
            return None
        clean = doi.strip().lower()
        clean = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', clean)
        clean = re.sub(r'^doi:\s*', '', clean)
        return clean if clean.startswith("10.") else None

    @classmethod
    def deduplicate_candidates(cls, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicates candidates across multi-provider sources using normalized DOI and canonical title matching."""
        seen_dois = set()
        seen_titles = set()
        deduped = []

        for cand in candidates:
            if not isinstance(cand, dict):
                continue

            raw_doi = cand.get("doi")
            norm_doi = cls.normalize_doi(raw_doi)
            norm_title = re.sub(r'\s+', ' ', (cand.get("title") or "").strip().lower())

            if norm_doi:
                if norm_doi in seen_dois:
                    continue
                seen_dois.add(norm_doi)
                cand["doi"] = norm_doi

            if norm_title and len(norm_title) >= 10:
                if norm_title in seen_titles:
                    continue
                seen_titles.add(norm_title)

            deduped.append(cand)

        return deduped

    def select_best_candidate(self, cit: Citation, candidates: List[Dict[str, Any]], min_score: Optional[float] = None) -> Optional[Dict[str, Any]]:
        if min_score is None:
            min_score = GuardrailConfig.REFERENCE_MIN_SCORE

        if not candidates:
            return None

        clean_cands = self.deduplicate_candidates(candidates)

        scored = []
        for cand in clean_cands:
            if isinstance(cand, dict):
                score, meta = self.compute_candidate_score(cit, cand)
                if score >= min_score:
                    scored.append((score, cand, meta))

        if not scored:
            return None

        scored.sort(key=lambda x: x[0], reverse=True)
        top1_score, top1_cand, top1_meta = scored[0]

        # Stage 4: Margin & Confidence Assessment
        margin = (top1_score - scored[1][0]) if len(scored) > 1 else 1.0
        
        if top1_score >= GuardrailConfig.REFERENCE_HIGH_CONFIDENCE and margin >= GuardrailConfig.REFERENCE_HIGH_MARGIN:
            confidence_level = "HIGH"
        elif top1_score >= GuardrailConfig.REFERENCE_MEDIUM_CONFIDENCE and margin >= GuardrailConfig.REFERENCE_MEDIUM_MARGIN:
            confidence_level = "MEDIUM"
        else:
            confidence_level = "UNCERTAIN"

        top1_cand["match_score"] = top1_score
        top1_cand["match_confidence"] = confidence_level
        top1_cand["match_margin"] = round(margin, 3)
        top1_cand["resolution_metadata"] = {
            "reference_confidence": top1_score,
            "title_score": top1_meta.get("title_score", 0.0),
            "author_score": top1_meta.get("author_score", 0.0),
            "year_score": top1_meta.get("year_score"),
            "venue_score": top1_meta.get("venue_score", 0.0),
            "rank_margin": round(margin, 3),
            "resolver": "global_rerank"
        }
        if confidence_level == "UNCERTAIN":
            top1_cand["is_uncertain"] = True
            top1_cand["ambiguous_candidates"] = [
                {
                    "title": c.get("title"),
                    "doi": c.get("doi"),
                    "score": s,
                    "source": c.get("source", "API Database")
                }
                for s, c, _ in scored[:2]
            ]
        return top1_cand
