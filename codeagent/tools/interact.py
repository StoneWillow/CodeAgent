from __future__ import annotations

import json
from typing import Callable

from codeagent.tools.registry import ToolRegistry

AskUser = Callable[[str, list[str] | None, bool], str]


def _parse_options(raw: str | None) -> list[str] | None:
    if raw is None or not str(raw).strip():
        return None
    text = str(raw).strip()
    if text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [str(x) for x in data]
        except json.JSONDecodeError:
            pass
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines or None


def register_interact_tool(
    registry: ToolRegistry,
    ask_user: AskUser | None = None,
) -> None:
    @registry.tool
    def AskUserQuestion(
        question: str,
        options: str | None = None,
        allow_multiple: bool = False,
    ) -> str:
        """向用户提问。无 options 时自由输入；有 options 时单选或多选。"""
        if ask_user is None:
            return "错误：当前环境无法向用户提问（未配置交互回调）。"
        opts = _parse_options(options)
        answer = ask_user(question, opts, allow_multiple)
        return f"用户回答: {answer}"
