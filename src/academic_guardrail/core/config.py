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
    REFERENCE_EARLY_EXIT_SCORE: float = 0.80      # Qualified winner racing early-exit score
    REFERENCE_TITLE_HARD_FLOOR: float = 0.30       # Minimum reliable title similarity floor

    # ── Claim Alignment & Polarity Thresholds ──
    STRONG_ALIGNMENT_THRESHOLD: float = 0.50       # Tier boundary for SUPPORTED (High Alignment)
    WEAK_ALIGNMENT_THRESHOLD: float = 0.30         # Tier boundary for PARTIAL (Moderate Alignment)
    POLARITY_CONTRADICTION_SCORE: float = 0.15     # Default score returned on explicit polarity inversion
