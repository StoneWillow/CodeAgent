from __future__ import annotations

from pathlib import Path

from codeagent.config import Settings, load_settings
from codeagent.llm.base import LLMClient
from codeagent.tools.base import Tool
from codeagent.tools.bash import ConfirmBash, register_bash_tool
from codeagent.tools.decorator import FunctionTool, tool
from codeagent.tools.files import register_explore_tools, register_file_tools
from codeagent.tools.interact import AskUser, register_interact_tool
from codeagent.tools.notebook import register_notebook_tool
from codeagent.tools.registry import ToolRegistry
from codeagent.tools.subagent import SubToolListener, register_task_tool
from codeagent.tools.todo import TodoStore, register_todo_tool
from codeagent.tools.workspace import Workspace

__all__ = [
    "Tool",
    "FunctionTool",
    "ToolRegistry",
    "Workspace",
    "TodoStore",
    "AskUser",
    "ConfirmBash",
    "SubToolListener",
    "tool",
    "build_default_registry",
    "build_explore_registry",
]


def build_explore_registry(workspace: Path) -> ToolRegistry:
    """Read-only tool set for sub-agents (Glob/Grep/Read only)."""
    ws = Workspace(workspace)
    registry = ToolRegistry()
    register_explore_tools(registry, ws)
    return registry


def build_default_registry(
    workspace: Path,
    *,
    settings: Settings | None = None,
    ask_user: AskUser | None = None,
    confirm_bash: ConfirmBash | None = None,
    todo_store: TodoStore | None = None,
    include_task: bool = True,
    on_sub_tool: SubToolListener | None = None,
    llm: LLMClient | None = None,
) -> ToolRegistry:
    ws = Workspace(workspace)
    registry = ToolRegistry()
    store = todo_store or TodoStore()
    register_file_tools(registry, ws)
    register_bash_tool(registry, ws, confirm_bash=confirm_bash)
    register_interact_tool(registry, ask_user=ask_user)
    register_todo_tool(registry, store)
    register_notebook_tool(registry, ws)
    if include_task:
        cfg = settings or load_settings()
        register_task_tool(
            registry,
            settings=cfg,
            parent_ws=ws,
            on_sub_tool=on_sub_tool,
            llm=llm,
        )
    return registry
