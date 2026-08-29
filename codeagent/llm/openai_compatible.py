from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from codeagent.llm.base import ChatResult, TextDeltaListener, ToolCall


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
                id=item["id"],
                name=item["name"],
                arguments=_parse_arguments(item["arguments"]),
            )
            for item in ordered
        ]
        raw: dict[str, Any] = {"role": "assistant", "content": content}
        if ordered:
            raw["tool_calls"] = [
                {
                    "id": item["id"],
                    "type": "function",
                    "function": {
                        "name": item["name"],
                        "arguments": item["arguments"],
                    },
                }
                for item in ordered
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
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        on_text_delta: TextDeltaListener | None = None,
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
