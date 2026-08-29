from __future__ import annotations

from pathlib import Path

from codeagent.memory.store import MemoryStore
from codeagent.prompts.templates import build_system_prompt


class PromptManager:
    """Assembles system prompt + rule-style memory blocks."""

    def __init__(
        self,
        system_prompt: str | None = None,
        workspace: Path | None = None,
        memory: MemoryStore | None = None,
    ) -> None:
        self._workspace = workspace
        if workspace is not None:
            self._memory = memory or MemoryStore(workspace)
        else:
            self._memory = memory
        if system_prompt is not None:
            self._system_prompt = system_prompt
        elif workspace is not None:
            self._system_prompt = self.full_system()
        else:
            from codeagent.config import load_settings

            settings = load_settings()
            self._workspace = settings.workspace
            self._memory = memory or MemoryStore(settings.workspace)
            self._system_prompt = self.full_system()

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    def full_system(self) -> str:
        if self._workspace is None:
            return self._system_prompt
        base = build_system_prompt(self._workspace)
        parts = [base]
        if self._memory is not None:
            long_term = self._memory.read_long_term()
            short_term = self._memory.read_short_term()
            if long_term:
                parts.append("# 长期记忆\n" + "\n".join(long_term))
            if short_term:
                parts.append("# 短期记忆\n" + "\n".join(short_term))
        return "\n\n".join(parts)

    def refresh_system(self) -> None:
        self._system_prompt = self.full_system()

    def set_system_prompt(self, text: str) -> None:
        self._system_prompt = text

    def extra_messages(self) -> list[dict]:
        return []
