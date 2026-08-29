from __future__ import annotations

import json
from dataclasses import dataclass, field

from codeagent.tools.registry import ToolRegistry

_VALID_STATUS = {"pending", "in_progress", "completed", "cancelled"}


@dataclass
class TodoItem:
    id: str
    content: str
    status: str = "pending"


@dataclass
class TodoStore:
    items: dict[str, TodoItem] = field(default_factory=dict)

    def merge(self, todos: list[dict]) -> str:
        for raw in todos:
            if not isinstance(raw, dict):
                continue
            todo_id = str(raw.get("id") or "").strip()
            if not todo_id:
                continue
            content = str(raw.get("content") or self.items.get(todo_id, TodoItem(todo_id, "")).content)
            status = str(raw.get("status") or "pending")
            if status not in _VALID_STATUS:
                status = "pending"
            self.items[todo_id] = TodoItem(id=todo_id, content=content, status=status)

        in_progress = [t for t in self.items.values() if t.status == "in_progress"]
        if len(in_progress) > 1:
            keep = in_progress[0].id
            for item in self.items.values():
                if item.status == "in_progress" and item.id != keep:
                    item.status = "pending"

        return self.format_list()

    def format_list(self) -> str:
        if not self.items:
            return "(任务列表为空)"
        lines = ["当前任务列表:"]
        order = ["in_progress", "pending", "completed", "cancelled"]
        sorted_items = sorted(
            self.items.values(),
            key=lambda t: (order.index(t.status) if t.status in order else 99, t.id),
        )
        for item in sorted_items:
            lines.append(f"- [{item.status}] {item.id}: {item.content}")
        return "\n".join(lines)


def register_todo_tool(registry: ToolRegistry, store: TodoStore) -> None:
    @registry.tool
    def TodoWrite(todos: str) -> str:
        """创建或更新任务列表。todos 为 JSON 数组，每项含 id/content/status。"""
        try:
            data = json.loads(todos)
        except json.JSONDecodeError as exc:
            return f"错误：todos 不是合法 JSON: {exc}"
        if not isinstance(data, list):
            return "错误：todos 必须是 JSON 数组。"
        return store.merge(data)
