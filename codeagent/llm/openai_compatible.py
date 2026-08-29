from __future__ import annotations

import json
import time
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from codeagent.llm.base import ChatResult, TextDeltaListener, ToolCall
from codeagent.llm.errors import ContextLengthAPIError, LLMRequestError

_MAX_RETRIES = 3
_RETRY_BASE_SECONDS = 1.0


def _parse_arguments(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    raw = raw.strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}
    return data if isinstance(data, dict) else {"_raw": data}


def _is_context_length_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(
        token in text
        for token in (
            "context_length_exceeded",
            "maximum context length",
            "context window",
            "too many tokens",
            "prompt is too long",
        )
    )


class _StreamAccumulator:
    """Rebuild a full assistant message from Chat Completions stream chunks."""

    def __init__(self) -> None:
        self._content: list[str] = []
        self._tools: dict[int, dict[str, str]] = {}
        self.finish_reason = "stop"

    def ingest(self, chunk: Any) -> str:
        if not getattr(chunk, "choices", None):
            return ""
        choice = chunk.choices[0]
        if choice.finish_reason:
            self.finish_reason = choice.finish_reason
        delta = choice.delta
        if delta is None:
            return ""
        text = delta.content or ""
        if text:
            self._content.append(text)
        for tc in getattr(delta, "tool_calls", None) or []:
            entry = self._tools.setdefault(
                tc.index, {"id": "", "name": "", "arguments": ""}
            )
            if tc.id:
                entry["id"] = tc.id
            fn = tc.function
            if fn is None:
                continue
            if fn.name:
                entry["name"] += fn.name
            if fn.arguments:
                entry["arguments"] += fn.arguments
        return text

    def to_result(self) -> ChatResult:
        content = "".join(self._content) or None
        ordered = [self._tools[i] for i in sorted(self._tools)]
        tool_calls = [
            ToolCall(
                id=item["id"] or f"call_{i}",
                name=item["name"],
                arguments=_parse_arguments(item["arguments"]),
            )
            for i, item in enumerate(ordered)
        ]
        raw: dict[str, Any] = {"role": "assistant", "content": content}
        if ordered:
            raw["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": item["name"],
                        "arguments": item["arguments"],
                    },
                }
                for tc, item in zip(tool_calls, ordered)
            ]
        return ChatResult(
            content=content,
            tool_calls=tool_calls,
            finish_reason=self.finish_reason,
            raw_message=raw,
        )


class OpenAICompatibleClient:
    """Chat Completions client for DeepSeek and other OpenAI-compatible APIs."""

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self._model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=60.0)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        on_text_delta: TextDeltaListener | None = None,
    ) -> ChatResult:
        last_error: BaseException | None = None
        emitted = False

        def wrapped_delta(text: str) -> None:
            nonlocal emitted
            emitted = True
            if on_text_delta is not None:
                on_text_delta(text)

        for attempt in range(_MAX_RETRIES):
            try:
                return self._chat_once(messages, tools, wrapped_delta)
            except ContextLengthAPIError:
                raise
            except (APITimeoutError, APIConnectionError, RateLimitError) as exc:
                last_error = exc
            except APIStatusError as exc:
                if _is_context_length_error(exc):
                    raise ContextLengthAPIError(str(exc)) from exc
                status = getattr(exc, "status_code", None)
                if status is not None and status < 500:
                    raise LLMRequestError(str(exc)) from exc
                last_error = exc
            except Exception as exc:
                if _is_context_length_error(exc):
                    raise ContextLengthAPIError(str(exc)) from exc
                last_error = exc

            if emitted:
                break
            time.sleep(_RETRY_BASE_SECONDS * (2**attempt))

        raise LLMRequestError(f"模型请求失败（已重试 {_MAX_RETRIES} 次）: {last_error}")

    def _chat_once(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        on_text_delta: TextDeltaListener | None,
    ) -> ChatResult:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
        stream = self._client.chat.completions.create(**kwargs)
        acc = _StreamAccumulator()
        for chunk in stream:
            text = acc.ingest(chunk)
            if text and on_text_delta is not None:
                on_text_delta(text)
        return acc.to_result()
