from __future__ import annotations

from pathlib import Path

from codeagent.prompts.templates import build_system_prompt


class PromptManager:
    """Owns the system prompt. Later this becomes memory management:

    retrieved notes, conversation summaries, and other injected context
    should be assembled here instead of inside the ReAct loop.
    """

    def __init__(
        self,
        system_prompt: str | None = None,
        workspace: Path | None = None,
    ) -> None:
        if system_prompt is not None:
            self._system_prompt = system_prompt
        elif workspace is not None:
            self._system_prompt = build_system_prompt(workspace)
        else:
            from codeagent.config import load_settings

            self._system_prompt = build_system_prompt(load_settings().workspace)

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    def set_system_prompt(self, text: str) -> None:
        self._system_prompt = text

    def extra_messages(self) -> list[dict]:
        """Hook for future memory items inserted after the system prompt."""
        return []
