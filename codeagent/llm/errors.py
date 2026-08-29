from __future__ import annotations


class ContextLengthAPIError(Exception):
    """The API rejected the request as over the model context window."""


class LLMRequestError(Exception):
    """Non-retryable or exhausted LLM failure."""
