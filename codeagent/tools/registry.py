from __future__ import annotations

from typing import Any, Callable

from codeagent.tools.base import Tool
from codeagent.tools.decorator import FunctionTool, tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool_obj: Tool) -> Tool:
        if not tool_obj.name:
            raise ValueError("tool.name 不能为空")
        self._tools[tool_obj.name] = tool_obj
        return tool_obj

    def tool(
        self,
        func: Callable[..., Any] | None = None,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Callable[..., Any] | Tool:
        def decorator(fn: Callable[..., Any]) -> Tool:
            return self.register(FunctionTool(fn, name=name, description=description))

        if func is not None:
            return decorator(func)
        return decorator

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        return [tool_obj.schema() for tool_obj in self._tools.values()]

    def execute(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        tool_obj = self._tools.get(name)
        if tool_obj is None:
            return f"未知工具: {name}"
        return tool_obj.execute(arguments or {})


__all__ = ["ToolRegistry", "tool"]
