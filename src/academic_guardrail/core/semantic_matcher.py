"""Semantic Matcher supporting lightweight CPU sentence-transformers embedding & fallback cross-lingual alignment."""

import re
import difflib
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer, util
    _HAS_ST = True
except ImportError:
    _HAS_ST = False
    logger.warning(
        "[academic_guardrail] sentence-transformers is NOT installed. "
        "Semantic matching will fall back to rule-based cross-lingual alignment, "
        "which is significantly weaker. "
        "Install full feature set with:  pip install 'mcp-academic-guardrail[full]'"
    )


class SemanticMatcher:
    """Computes semantic embedding similarity between claims and abstract sentences."""

    def __init__(self, model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"):
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        if _HAS_ST and self._model is None:
            try:
                self._model = SentenceTransformer(self.model_name)
            except Exception:
                self._model = False
        return self._model if self._model else None

    def compute_similarity(self, text_a: str, text_b: str) -> float:
        if not text_a or not text_b:
            return 0.0

        model = self._get_model()
        if model:
            try:
                emb_a = model.encode(text_a, convert_to_tensor=True)
                emb_b = model.encode(text_b, convert_to_tensor=True)
                sim = float(util.cos_sim(emb_a, emb_b)[0][0])
                return round(max(0.0, min(1.0, sim)), 2)
            except Exception:
                pass

        # Fallback Engine: Cross-Lingual Concept & Keyphrase Density Alignment
        return self._fallback_cross_lingual_similarity(text_a, text_b)

    def _fallback_cross_lingual_similarity(self, claim: str, target: str) -> float:
        """Rule-based cross-lingual concept mapping fallback when sentence-transformers is absent."""
        c = claim.lower()
        t = target.lower()

        # Direct string ratio
        raw_ratio = difflib.SequenceMatcher(None, c, t).ratio()

        # Bimodal Concept Anchor Dictionary
        CN_EN_DICTIONARY = [
            ({"人工智能", "ai", "智能"}, {"artificial intelligence", "ai", "machine learning", "deep learning"}),
            ({"劳动力", "就业", "失业", "岗位", "人才", "招聘"}, {"labor", "labour", "employment", "unemployment", "job", "jobs", "worker", "workers", "workforce", "hiring"}),
            ({"匹配", "结构", "偏向"}, {"match", "matching", "structure", "structural", "skill", "skills", "mismatch", "bias", "biased"}),
            ({"技术", "自动化", "创新"}, {"technology", "technologies", "tech", "automation", "automate", "automated", "innovation"}),
            ({"生产率", "效率", "经济", "增长"}, {"productivity", "efficiency", "economic", "growth", "output"}),
            ({"金融", "数字金融", "数字经济"}, {"finance", "financial", "digital finance", "digital economy"}),
            ({"空间", "流动", "迁移", "偏好"}, {"spatial", "space", "mobility", "migration", "migrate", "preference"}),
        ]

        concept_matches = 0
        total_concepts = 0
        for cn_set, en_set in CN_EN_DICTIONARY:
            claim_has = any(w in c for w in cn_set.union(en_set))
            target_has = any(w in t for w in en_set.union(cn_set))
            if claim_has or target_has:
                total_concepts += 1
                if claim_has and target_has:
                    concept_matches += 1

        if total_concepts > 0:
            concept_score = concept_matches / float(total_concepts)
            score = 0.70 * concept_score + 0.30 * raw_ratio
        else:
            # General domain fallback (token overlap + sequence ratio)
            words_c = set(re.findall(r'\b\w{3,}\b', c))
            words_t = set(re.findall(r'\b\w{3,}\b', t))
            overlap = (len(words_c.intersection(words_t)) / float(max(len(words_c), 1))) if words_c and words_t else 0.0
            score = 0.50 * overlap + 0.50 * raw_ratio

        return round(min(1.0, score), 2)
