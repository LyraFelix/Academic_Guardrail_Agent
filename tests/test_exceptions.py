"""Unit tests for custom exception hierarchy."""

import pytest
from academic_guardrail.core.exceptions import (
    AcademicGuardrailError, ParserError, ProviderError, RateLimitError, VerificationError
)


def test_exception_hierarchy():
    assert issubclass(ParserError, AcademicGuardrailError)
    assert issubclass(ProviderError, AcademicGuardrailError)
    assert issubclass(RateLimitError, ProviderError)
    assert issubclass(VerificationError, AcademicGuardrailError)


def test_exception_raising():
    with pytest.raises(ProviderError) as exc_info:
        raise ProviderError("OpenAlex API down")
    assert "OpenAlex API down" in str(exc_info.value)
    assert isinstance(exc_info.value, AcademicGuardrailError)


def test_rate_limit_exception():
    with pytest.raises(ProviderError):
        raise RateLimitError("HTTP 429")
