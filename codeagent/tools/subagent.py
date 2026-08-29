from __future__ import annotations

import contextvars
import tempfile
from pathlib import Path
from typing import Any, Callable

from codeagent.config import Settings
from codeagent.conversation import Conversation
from codeagent.llm.base import LLMClient
from codeagent.memory.tiered import TieredMemory
from codeagent.prompts.manager import PromptManager
from codeagent.prompts.templates import build_subagent_system_prompt
from codeagent.tools.errors import ERROR_DENIED, ERROR_INVALID_ARGS, format_error
from codeagent.tools.registry import ToolRegistry
from codeagent.tools.workspace import Workspace

SubToolListener = Callable[[str, dict[str, Any]], None]

_agent_depth: contextvars.ContextVar[int] = contextvars.ContextVar("agent_depth", default=0)


def register_task_tool(
    registry: ToolRegistry,
    *,
    settings: Settings,
    parent_ws: Workspace,
    on_sub_tool: SubToolListener | None = None,
    llm: LLMClient | None = None,
) -> None:
    @registry.tool
    def Task(prompt: str, path: str = ".") -> str:
        """启动只读子 Agent 探索代码并返回摘要。仅 Glob/Grep/Read；不能改文件、不能递归调用 Task。"""
        from codeagent.agent import Agent

        if _agent_depth.get() > 0:
            return format_error(ERROR_DENIED, "子 Agent 禁止再调用 Task")

        task_prompt = (prompt or "").strip()
        if not task_prompt:
            return format_error(ERROR_INVALID_ARGS, "prompt 不能为空")

        resolved = parent_ws.resolve(path)
        if isinstance(resolved, str):
            return resolved
        if not resolved.exists():
            return f"错误：路径不存在: {path}"
        if not resolved.is_dir():
            return f"错误：path 必须是目录: {path}"

        sub_root = resolved
        from codeagent.tools import build_explore_registry

        explore_tools = build_explore_registry(sub_root)

        token = _agent_depth.set(_agent_depth.get() + 1)
        try:
            with tempfile.TemporaryDirectory(prefix="codeagent-sub-mem-") as td:
                mem_root = Path(td)
                ephemeral_memory = TieredMemory(mem_root, mem_root / "global")
                system = build_subagent_system_prompt(sub_root)
                sub_prompts = PromptManager(
                    system_prompt=system,
                    workspace=sub_root,
                    memory=ephemeral_memory,
                    global_memory_dir=mem_root / "global",
                )

                sub_agent = Agent.from_settings(
                    settings,
                    tools=explore_tools,
                    prompts=sub_prompts,
                    conversation=Conversation(system),
                    memory=ephemeral_memory,
                    max_turns=settings.subagent_max_turns,
                    llm=llm,
                )

                def sub_tool_cb(name: str, args: dict[str, Any]) -> None:
                    if on_sub_tool is not None:
                        on_sub_tool(name, args)

                return sub_agent.run(task_prompt, on_tool=sub_tool_cb)
        finally:
            _agent_depth.reset(token)
