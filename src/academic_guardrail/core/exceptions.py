"""Custom exception hierarchy for Academic Guardrail Agent."""

class AcademicGuardrailError(Exception):
    """Base exception for all Academic Guardrail errors."""
    pass


class ParserError(AcademicGuardrailError):
    """Raised when document parsing or citation extraction fails."""
    pass


class ProviderError(AcademicGuardrailError):
    """Raised when online database lookup (OpenAlex, Crossref, etc.) encounters an API or network error."""
    pass


class RateLimitError(ProviderError):
    """Raised when an online database provider triggers HTTP 429 Too Many Requests."""
    pass


class VerificationError(AcademicGuardrailError):
    """Raised when claim alignment or citation verification logic fails unexpectedly."""
    pass
