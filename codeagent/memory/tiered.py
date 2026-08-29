from __future__ import annotations

from pathlib import Path

_MAX_GLOBAL = 20

# Re-export workspace helpers for single-file stores.
from codeagent.memory.store import (  # noqa: F401
    MemoryStore,
    _normalize_rules,
    _read_rules,
    _write_rules,
)


class GlobalMemoryStore:
    """Cross-workspace memory under project `.agent/memory/global.txt`."""

    def __init__(self, root: Path) -> None:
        self._path = root / "global.txt"

    def read(self) -> list[str]:
        return _read_rules(self._path)

    def merge(self, new_rules: list[str]) -> list[str]:
        existing = self.read()
        seen = {r.lower() for r in existing}
        merged = list(existing)
        for rule in _normalize_rules(new_rules):
            key = rule.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(rule)
        merged = merged[:_MAX_GLOBAL]
        _write_rules(self._path, merged)
        return merged


class TieredMemory:
    """三层记忆：全局 → 工作区 → 会话（注入 system 时由广到专）。"""

    def __init__(
        self,
        workspace: Path,
        global_dir: Path,
        session_rules: list[str] | None = None,
    ) -> None:
        self._workspace = MemoryStore(workspace)
        self._global = GlobalMemoryStore(global_dir)
        self.session: list[str] = _normalize_rules(list(session_rules or []))[:10]

    @property
    def workspace_store(self) -> MemoryStore:
        return self._workspace

    @property
    def global_store(self) -> GlobalMemoryStore:
        return self._global

    def write_session(self, rules: list[str]) -> list[str]:
        self.session = _normalize_rules(rules)[:10]
        return self.session

    def write_workspace_short(self, rules: list[str]) -> list[str]:
        return self._workspace.write_short_term(rules)

    def merge_workspace_long(self, rules: list[str]) -> list[str]:
        return self._workspace.merge_long_term(rules)

    def merge_global(self, rules: list[str]) -> list[str]:
        return self._global.merge(rules)

    def prompt_sections(self) -> list[tuple[str, list[str]]]:
        sections: list[tuple[str, list[str]]] = []
        global_rules = self._global.read()
        if global_rules:
            sections.append(("全局记忆", global_rules))

        workspace_rules = self._workspace.read_long_term() + self._workspace.read_short_term()
        if workspace_rules:
            sections.append(("工作区记忆", workspace_rules))

        if self.session:
            sections.append(("会话记忆", self.session))
        return sections
