from __future__ import annotations

from typing import Any


class Conversation:
    """In-memory chat history. Source of truth for context.

    System message stays at index 0. Messages are plain dicts aligned with
    the OpenAI-compatible Chat Completions schema so later sessions can
    dump/load JSON without conversion.
    """

    def __init__(self, system_prompt: str) -> None:
        self._messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]

    def add_user(self, content: str) -> None:
        self._messages.append({"role": "user", "content": content})

    def add_assistant(self, message: dict[str, Any]) -> None:
        payload = dict(message)
        payload.setdefault("role", "assistant")
        self._messages.append(payload)

    def add_tool_result(self, tool_call_id: str, content: str, name: str | None = None) -> None:
        item: dict[str, Any] = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        }
        if name:
            item["name"] = name
        self._messages.append(item)

    def to_messages(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._messages]

    def approx_chars(self) -> int:
        total = 0
        for item in self._messages:
            total += len(str(item.get("content") or ""))
        return total

    def to_dict(self) -> dict[str, Any]:
        return {"messages": self.to_messages()}

    def set_system(self, content: str) -> None:
        if self._messages and self._messages[0].get("role") == "system":
            self._messages[0] = {"role": "system", "content": content}
        else:
            self._messages.insert(0, {"role": "system", "content": content})

    def replace_with_snapshot(self, system: str, snapshot: str) -> None:
        self._messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"[会话快照]\n{snapshot}"},
        ]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Conversation:
        messages = data.get("messages") or []
        if not messages or messages[0].get("role") != "system":
            raise ValueError("conversation JSON must start with a system message")
        conv = cls(system_prompt=messages[0].get("content") or "")
        conv._messages = [dict(item) for item in messages]
        return conv
