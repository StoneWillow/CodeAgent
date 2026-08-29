from __future__ import annotations

from pathlib import Path

_MAX_LONG = 12
_MAX_SHORT = 10
_MAX_RULE_CHARS = 120


def _normalize_rules(lines: list[str]) -> list[str]:
    out: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if not line.startswith("- "):
            line = f"- {line.lstrip('-').strip()}"
        if len(line) > _MAX_RULE_CHARS + 2:
            line = line[: _MAX_RULE_CHARS + 2] + "..."
        out.append(line)
    return out


def _read_rules(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines = [
        ln.strip()
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    return _normalize_rules(lines)


def _write_rules(path: Path, rules: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_rules(rules)
    path.write_text("\n".join(normalized) + ("\n" if normalized else ""), encoding="utf-8")


class MemoryStore:
    """Rule-style short/long memory persisted under workspace/.agent/memory/."""

    def __init__(self, workspace: Path) -> None:
        self._dir = workspace / ".agent" / "memory"
        self._long_path = self._dir / "long_term.txt"
        self._short_path = self._dir / "short_term.txt"

    def read_long_term(self) -> list[str]:
        return _read_rules(self._long_path)

    def read_short_term(self) -> list[str]:
        return _read_rules(self._short_path)

    def merge_long_term(self, new_rules: list[str]) -> list[str]:
        existing = self.read_long_term()
        seen = {r.lower() for r in existing}
        merged = list(existing)
        for rule in _normalize_rules(new_rules):
            key = rule.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(rule)
        merged = merged[:_MAX_LONG]
        _write_rules(self._long_path, merged)
        return merged

    def write_short_term(self, rules: list[str]) -> list[str]:
        rules = _normalize_rules(rules)[:_MAX_SHORT]
        _write_rules(self._short_path, rules)
        return rules
