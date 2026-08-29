from __future__ import annotations

# Observation prefixes so the model can distinguish failure kinds.
ERROR_INVALID_ARGS = "invalid_args"
ERROR_UNKNOWN = "unknown_tool"
ERROR_DENIED = "denied"
ERROR_NOT_FOUND = "not_found"
ERROR_TIMEOUT = "timeout"
ERROR_INTERNAL = "internal"
ERROR_CIRCUIT = "circuit"


def format_error(kind: str, message: str) -> str:
    return f"[error:{kind}] {message}"


def is_error_observation(text: str) -> bool:
    return text.startswith("[error:")


def error_kind(text: str) -> str:
    if not text.startswith("[error:"):
        return ""
    end = text.find("]")
    if end < 0:
        return ""
    return text[7:end]
