from __future__ import annotations

import inspect
from typing import Any, Callable, get_args, get_origin, get_type_hints

from codeagent.tools.base import Tool


def _unwrap_optional(annotation: Any) -> tuple[Any, bool]:
    origin = get_origin(annotation)
    if origin is None:
        return annotation, False
    args = get_args(annotation)
    if origin is type(None):
        return Any, True
    if type(None) in args:
        non_none = [a for a in args if a is not type(None)]
        return (non_none[0] if non_none else Any), True
    return annotation, False


def _annotation_to_json_type(annotation: Any) -> dict[str, Any]:
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {"type": "string"}
    base, _ = _unwrap_optional(annotation)
    if base is str:
        return {"type": "string"}
    if base is int:
        return {"type": "integer"}
    if base is bool:
        return {"type": "boolean"}
    if base is float:
        return {"type": "number"}
    return {"type": "string"}


def _build_parameters(func: Callable[..., Any]) -> dict[str, Any]:
    hints = get_type_hints(func)
    sig = inspect.signature(func)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        ann = hints.get(name, str)
        base, optional = _unwrap_optional(ann)
        prop = _annotation_to_json_type(base)
        if param.default is not inspect.Parameter.empty:
            if isinstance(param.default, bool):
                prop["default"] = param.default
            elif param.default is not None:
                prop["default"] = param.default
        else:
            if not optional:
                required.append(name)
        properties[name] = prop

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _build_description(func: Callable[..., Any]) -> str:
    doc = inspect.getdoc(func) or ""
    return doc.split("\n\n")[0].strip() or func.__name__


class FunctionTool(Tool):
    def __init__(
        self,
        func: Callable[..., Any],
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        self._func = func
        self.name = name or func.__name__
        self.description = description or _build_description(func)
        self.parameters = _build_parameters(func)

    def execute(self, arguments: dict[str, Any]) -> str:
        sig = inspect.signature(self._func)
        allowed = {
            name
            for name, param in sig.parameters.items()
            if param.kind
            not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        }
        kwargs = {k: v for k, v in (arguments or {}).items() if k in allowed}
        try:
            result = self._func(**kwargs)
            return str(result) if result is not None else ""
        except Exception as exc:
            return f"工具执行错误 ({self.name}): {exc}"


def tool(
    func: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Callable[..., Any] | FunctionTool:
    def decorator(fn: Callable[..., Any]) -> FunctionTool:
        return FunctionTool(fn, name=name, description=description)

    if func is not None:
        return decorator(func)
    return decorator
