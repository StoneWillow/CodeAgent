from __future__ import annotations

from codeagent.prompts.templates import DEFAULT_SYSTEM_PROMPT


class PromptManager:
    """Owns the system prompt. Later this becomes memory management:

    retrieved notes, conversation summaries, and other injected context
    should be assembled here instead of inside the ReAct loop.
    """

    def __init__(self, system_prompt: str | None = None) -> None:
        self._system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    def set_system_prompt(self, text: str) -> None:
        self._system_prompt = text

    def extra_messages(self) -> list[dict]:
        """Hook for future memory items inserted after the system prompt."""
        return []
