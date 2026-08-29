from __future__ import annotations

from typing import Any

from codeagent.tools.errors import ERROR_INVALID_ARGS, format_error


def _coerce(value: Any, json_type: str) -> tuple[Any, bool]:
    if json_type == "string":
        return str(value), True
    if json_type == "integer":
        if isinstance(value, bool):
            return None, False
        if isinstance(value, int):
            return value, True
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value), True
        return None, False
    if json_type == "number":
        if isinstance(value, bool):
            return None, False
        if isinstance(value, (int, float)):
            return float(value), True
        try:
            return float(value), True
        except (TypeError, ValueError):
            return None, False
    if json_type == "boolean":
        if isinstance(value, bool):
            return value, True
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower() == "true", True
        return None, False
    return value, True


def validate_arguments(
    parameters: dict[str, Any],
    arguments: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return (cleaned_args, error_message). error_message is None on success."""
    raw = dict(arguments or {})
    if "_raw" in raw and len(raw) == 1:
        return None, format_error(
            ERROR_INVALID_ARGS,
            "工具参数不是合法 JSON，请按 schema 重试。",
        )

    properties: dict[str, Any] = parameters.get("properties") or {}
    required = list(parameters.get("required") or [])

    missing = [name for name in required if name not in raw or raw[name] is None]
    if missing:
        return None, format_error(
            ERROR_INVALID_ARGS,
            f"缺少必填参数: {', '.join(missing)}。请补全后重试。",
        )

    cleaned: dict[str, Any] = {}
    for name, value in raw.items():
        if name not in properties:
            continue
        json_type = str((properties[name] or {}).get("type") or "string")
        coerced, ok = _coerce(value, json_type)
        if not ok:
            return None, format_error(
                ERROR_INVALID_ARGS,
                f"参数 {name} 类型应为 {json_type}，当前={value!r}。",
            )
        cleaned[name] = coerced
    return cleaned, None
