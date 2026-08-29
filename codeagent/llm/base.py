from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

TextDeltaListener = Callable[[str], None]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResult:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    raw_message: dict[str, Any] = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class LLMClient(Protocol):
    """Any chat model used by the agent. Add new vendors behind this shape."""

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        on_text_delta: TextDeltaListener | None = None,
    ) -> ChatResult: ...
