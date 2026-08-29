from __future__ import annotations

from pathlib import Path

from codeagent.memory.tiered import TieredMemory
from codeagent.prompts.templates import build_system_prompt


class PromptManager:
    """Assembles system prompt + tiered memory blocks."""

    def __init__(
        self,
        system_prompt: str | None = None,
        workspace: Path | None = None,
        memory: TieredMemory | None = None,
        global_memory_dir: Path | None = None,
    ) -> None:
        self._workspace = workspace
        self._tiered = memory
        if workspace is not None and self._tiered is None:
            if global_memory_dir is None:
                from codeagent.config import load_settings

                global_memory_dir = load_settings().global_memory_dir
            self._tiered = TieredMemory(workspace, global_memory_dir)
        if system_prompt is not None:
            self._system_prompt = system_prompt
        elif workspace is not None:
            self._system_prompt = self.full_system()
        else:
            from codeagent.config import load_settings

            settings = load_settings()
            self._workspace = settings.workspace
            self._tiered = TieredMemory(settings.workspace, settings.global_memory_dir)
            self._system_prompt = self.full_system()

    @property
    def memory(self) -> TieredMemory | None:
        return self._tiered

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    def full_system(self) -> str:
        if self._workspace is None:
            return self._system_prompt
        base = build_system_prompt(self._workspace)
        parts = [base]
        if self._tiered is not None:
            for title, rules in self._tiered.prompt_sections():
                parts.append(f"# {title}\n" + "\n".join(rules))
        return "\n\n".join(parts)

    def refresh_system(self) -> None:
        self._system_prompt = self.full_system()

    def set_system_prompt(self, text: str) -> None:
        self._system_prompt = text

    def extra_messages(self) -> list[dict]:
        return []
