from __future__ import annotations

from pathlib import Path
from typing import Callable

from codeagent.tools.base import Tool
from codeagent.tools.bash import ConfirmBash, register_bash_tool
from codeagent.tools.decorator import FunctionTool, tool
from codeagent.tools.files import register_file_tools
from codeagent.tools.interact import AskUser, register_interact_tool
from codeagent.tools.notebook import register_notebook_tool
from codeagent.tools.registry import ToolRegistry
from codeagent.tools.test import TestTool
from codeagent.tools.todo import TodoStore, register_todo_tool
from codeagent.tools.workspace import Workspace

__all__ = [
    "Tool",
    "FunctionTool",
    "ToolRegistry",
    "TestTool",
    "Workspace",
    "TodoStore",
    "AskUser",
    "ConfirmBash",
    "tool",
    "build_default_registry",
]


def build_default_registry(
    workspace: Path,
    *,
    ask_user: AskUser | None = None,
    confirm_bash: ConfirmBash | None = None,
    todo_store: TodoStore | None = None,
) -> ToolRegistry:
    ws = Workspace(workspace)
    registry = ToolRegistry()
    store = todo_store or TodoStore()
    register_file_tools(registry, ws)
    register_bash_tool(registry, ws, confirm_bash=confirm_bash)
    register_interact_tool(registry, ask_user=ask_user)
    register_todo_tool(registry, store)
    register_notebook_tool(registry, ws)
    registry.register(TestTool())
    return registry
