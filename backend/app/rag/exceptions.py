"""Custom exceptions for the RAG processing engine."""

from __future__ import annotations


class RAGError(Exception):
    """Base exception for all RAG pipeline errors."""


class InsufficientSourcesError(RAGError):
    """Raised when fewer than the configured minimum trusted sources survive validation.

    The pipeline must surface a "cannot verify" response to the user instead of
    allowing the LLM to answer without enough authoritative grounding.
    """

    def __init__(self, valid_count: int, required_count: int) -> None:
        self.valid_count = valid_count
        self.required_count = required_count
        super().__init__(
            f"Only {valid_count} trusted source(s) found, "
            f"but at least {required_count} are required."
        )


class RetrievalError(RAGError):
    """Raised when retrieval fails in a way callers should handle."""


class LLMError(RAGError):
    """Base exception for LLM client failures."""


class LLMRateLimitError(LLMError):
    """Raised when the LLM provider rate-limits the request."""


class LLMConnectionError(LLMError):
    """Raised when the LLM provider cannot be reached."""


class LLMAPIError(LLMError):
    """Raised on a generic LLM provider API error."""
