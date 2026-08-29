from __future__ import annotations

import json
from typing import Any

import tiktoken

_ENCODING = tiktoken.get_encoding("cl100k_base")

# Rough per-message overhead for chat format (role, separators).
_MESSAGE_OVERHEAD = 4


def _text_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_ENCODING.encode(text))


def _message_tokens(message: dict[str, Any]) -> int:
    total = _MESSAGE_OVERHEAD
    content = message.get("content")
    if content:
        total += _text_tokens(str(content))

    tool_calls = message.get("tool_calls") or []
    if tool_calls:
        total += _text_tokens(json.dumps(tool_calls, ensure_ascii=False))

    if message.get("tool_call_id"):
        total += _text_tokens(str(message.get("tool_call_id")))

    if message.get("name"):
        total += _text_tokens(str(message.get("name")))

    return total


def count_text_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_ENCODING.encode(text))


def count_messages(messages: list[dict[str, Any]]) -> int:
    return sum(_message_tokens(m) for m in messages)


def count_tools(tools: list[dict[str, Any]] | None) -> int:
    if not tools:
        return 0
    return _text_tokens(json.dumps(tools, ensure_ascii=False))


def count_request(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> int:
    return count_messages(messages) + count_tools(tools)
