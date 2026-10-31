"""Centralized System Thresholds and Configuration Constants for Academic Guardrail Agent."""

import os

class GuardrailConfig:
    """Centralized configuration class managing entity resolution and claim alignment thresholds."""

    # ── User Identity & API Polite Pool Email ──
    DEFAULT_EMAIL: str = os.environ.get("ACADEMIC_GUARDRAIL_EMAIL", "academic-guardrail@example.com")

    # ── Reference Entity Resolution & Ambiguity Thresholds ──
    REFERENCE_MIN_SCORE: float = 0.40             # Minimum acceptable entity resolution score
    REFERENCE_HIGH_CONFIDENCE: float = 0.75       # Score threshold for HIGH confidence match
    REFERENCE_HIGH_MARGIN: float = 0.10           # Margin threshold for HIGH confidence match
    REFERENCE_MEDIUM_CONFIDENCE: float = 0.60     # Score threshold for MEDIUM confidence match
    REFERENCE_MEDIUM_MARGIN: float = 0.05         # Margin threshold for MEDIUM confidence match
    REFERENCE_TITLE_HARD_FLOOR: float = 0.30       # Minimum reliable title similarity floor

    # Retrieval only; never a support/contradiction threshold.
    CLAIM_RETRIEVAL_MIN_SCORE: float = 0.15
