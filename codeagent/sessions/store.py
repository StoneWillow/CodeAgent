from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _title_from_messages(messages: list[dict[str, Any]]) -> str:
    for msg in messages:
        if msg.get("role") == "user":
            text = str(msg.get("content") or "").strip()
            if text.startswith("[会话快照]"):
                continue
            if text:
                one_line = text.replace("\n", " ")
                return one_line[:40] + ("…" if len(one_line) > 40 else "")
    return "新对话"


@dataclass
class SessionRecord:
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    todos: list[dict[str, Any]] = field(default_factory=list)
    memory: list[str] = field(default_factory=list)
    usage_tokens: int = 0
    context_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": self.messages,
            "todos": self.todos,
            "memory": self.memory,
            "usage_tokens": self.usage_tokens,
            "context_tokens": self.context_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionRecord:
        return cls(
            id=str(data.get("id") or ""),
            title=str(data.get("title") or "新对话"),
            created_at=str(data.get("created_at") or _now_iso()),
            updated_at=str(data.get("updated_at") or _now_iso()),
            messages=list(data.get("messages") or []),
            todos=list(data.get("todos") or []),
            memory=[str(x) for x in (data.get("memory") or [])],
            usage_tokens=max(0, int(data.get("usage_tokens") or 0)),
            context_tokens=max(0, int(data.get("context_tokens") or 0)),
        )


@dataclass
class SessionSummary:
    id: str
    title: str
    updated_at: str
    snippet: str = ""


class SessionStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def _path(self, session_id: str) -> Path:
        return self._root / f"{session_id}.json"

    def create(self, messages: list[dict[str, Any]] | None = None) -> SessionRecord:
        now = _now_iso()
        msgs = messages or []
        record = SessionRecord(
            id=uuid.uuid4().hex[:8],
            title=_title_from_messages(msgs) if msgs else "新对话",
            created_at=now,
            updated_at=now,
            messages=msgs,
            todos=[],
        )
        self.save(record)
        return record

    def save(self, record: SessionRecord) -> None:
        record.updated_at = _now_iso()
        if not record.title or record.title == "新对话":
            record.title = _title_from_messages(record.messages)
        path = self._path(record.id)
        path.write_text(
            json.dumps(record.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def load(self, session_id: str) -> SessionRecord | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return SessionRecord.from_dict(data)
        except (json.JSONDecodeError, OSError):
            return None

    def list(self) -> list[SessionSummary]:
        items: list[tuple[str, float, SessionSummary]] = []
        for path in self._root.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                record = SessionRecord.from_dict(data)
            except (json.JSONDecodeError, OSError):
                continue
            items.append(
                (
                    record.updated_at,
                    path.stat().st_mtime,
                    SessionSummary(
                        id=record.id,
                        title=record.title,
                        updated_at=record.updated_at,
                    ),
                )
            )
        items.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return [row[2] for row in items]

    def search(self, query: str) -> list[SessionSummary]:
        q = query.strip().lower()
        if not q:
            return self.list()
        hits: list[SessionSummary] = []
        for path in self._root.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                record = SessionRecord.from_dict(data)
            except (json.JSONDecodeError, OSError):
                continue
            snippet = _find_snippet(record, q)
            if snippet or q in record.title.lower():
                hits.append(
                    SessionSummary(
                        id=record.id,
                        title=record.title,
                        updated_at=record.updated_at,
                        snippet=snippet,
                    )
                )
        hits.sort(key=lambda s: s.updated_at, reverse=True)
        return hits


def _find_snippet(record: SessionRecord, query: str) -> str:
    for msg in record.messages:
        role = msg.get("role")
        if role not in {"user", "assistant"}:
            continue
        text = str(msg.get("content") or "")
        lowered = text.lower()
        idx = lowered.find(query)
        if idx < 0:
            continue
        start = max(0, idx - 30)
        end = min(len(text), idx + len(query) + 50)
        snippet = text[start:end].replace("\n", " ")
        if start > 0:
            snippet = "…" + snippet
        if end < len(text):
            snippet = snippet + "…"
        return snippet
    return ""
