from __future__ import annotations

from typing import Any, Callable

from codeagent.context.tokens import count_text_tokens
from codeagent.tools.base import Tool
from codeagent.tools.decorator import FunctionTool, tool
from codeagent.tools.errors import (
    ERROR_DENIED,
    ERROR_INTERNAL,
    ERROR_INVALID_ARGS,
    ERROR_NOT_FOUND,
    ERROR_TIMEOUT,
    ERROR_UNKNOWN,
    format_error,
    is_error_observation,
)
from codeagent.tools.validate import validate_arguments

_MAX_TOOL_OUTPUT_TOKENS = 8000
_MAX_FAIL_STREAK = 3


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._fail_streak: dict[str, int] = {}

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
            observation = format_error(ERROR_UNKNOWN, f"未知工具: {name}")
            self._note_failure(name, ERROR_UNKNOWN)
            return observation

        kind = self._circuit_kind(name)
        if kind and self._fail_streak.get(f"{name}:{kind}", 0) >= _MAX_FAIL_STREAK:
            return format_error(
                "circuit",
                f"{name} 连续失败 {self._fail_streak[f'{name}:{kind}']} 次（{kind}）。"
                f"请改用其它工具或策略，不要重复同一调用。",
            )

        cleaned, err = validate_arguments(tool_obj.parameters, arguments)
        if err:
            self._note_failure(name, ERROR_INVALID_ARGS)
            return err

        try:
            observation = tool_obj.execute(cleaned or {})
        except Exception as exc:
            observation = format_error(ERROR_INTERNAL, f"{name}: {exc}")

        observation = _classify_observation(observation)
        observation = _truncate_observation(observation)

        if is_error_observation(observation):
            self._note_failure(name, _kind_of(observation))
        else:
            self._clear_failures(name)
        return observation

    def _circuit_kind(self, name: str) -> str | None:
        prefix = f"{name}:"
        best: str | None = None
        best_n = 0
        for key, n in self._fail_streak.items():
            if key.startswith(prefix) and n > best_n:
                best = key.split(":", 1)[1]
                best_n = n
        return best

    def _note_failure(self, name: str, kind: str) -> None:
        key = f"{name}:{kind}"
        self._fail_streak[key] = self._fail_streak.get(key, 0) + 1

    def _clear_failures(self, name: str) -> None:
        drop = [k for k in self._fail_streak if k.startswith(f"{name}:")]
        for k in drop:
            del self._fail_streak[k]


def _kind_of(text: str) -> str:
    if text.startswith("[error:"):
        end = text.find("]")
        if end > 0:
            return text[7:end]
    return ERROR_INTERNAL


def _classify_observation(text: str) -> str:
    if is_error_observation(text):
        return text
    lowered = text.lower()
    if text.startswith("拒绝执行") or "路径越界" in text:
        return format_error(ERROR_DENIED, text)
    if "不存在" in text or "not found" in lowered:
        return format_error(ERROR_NOT_FOUND, text)
    if "超时" in text or "timeout" in lowered:
        return format_error(ERROR_TIMEOUT, text)
    if text.startswith("错误：") or text.startswith("工具执行错误"):
        return format_error(ERROR_INTERNAL, text)
    return text


def _truncate_observation(text: str) -> str:
    tokens = count_text_tokens(text)
    if tokens <= _MAX_TOOL_OUTPUT_TOKENS:
        return text
    # Approximate cut: 4 chars/token is conservative for mixed CJK.
    keep_chars = max(400, int(len(text) * _MAX_TOOL_OUTPUT_TOKENS / tokens))
    return (
        text[:keep_chars]
        + f"\n...(输出已截断，约 {tokens} token，上限 {_MAX_TOOL_OUTPUT_TOKENS}。"
        + "请用 offset/limit 或更精确的路径续读。)"
    )


__all__ = ["ToolRegistry", "tool"]
