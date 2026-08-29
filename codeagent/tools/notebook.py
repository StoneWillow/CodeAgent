from __future__ import annotations

import json
from pathlib import Path

from codeagent.tools.registry import ToolRegistry
from codeagent.tools.workspace import Workspace

_LANG_TO_CELL = {
    "python": "code",
    "code": "code",
    "markdown": "markdown",
    "md": "markdown",
    "raw": "raw",
}


def _source_to_list(text: str) -> list[str]:
    if not text:
        return []
    if text.endswith("\n"):
        lines = text.splitlines(keepends=True)
        return lines if lines else [text]
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] = lines[-1] + "\n"
    return lines if lines else [text + "\n"]


def _new_cell(cell_type: str, source: str) -> dict:
    return {
        "cell_type": cell_type,
        "metadata": {},
        "source": _source_to_list(source),
    }


def register_notebook_tool(registry: ToolRegistry, ws: Workspace) -> None:
    @registry.tool
    def NotebookEdit(
        path: str,
        cell_idx: int,
        new_source: str,
        is_new_cell: bool = False,
        cell_language: str = "python",
    ) -> str:
        """编辑 Jupyter notebook 的 cell。不执行 kernel。"""
        resolved = ws.resolve(path)
        if isinstance(resolved, str):
            return resolved
        if resolved.suffix.lower() != ".ipynb":
            return "错误：NotebookEdit 仅支持 .ipynb 文件。"

        cell_type = _LANG_TO_CELL.get(cell_language.lower(), "code")
        if cell_idx < 0:
            return "错误：cell_idx 不能为负数。"

        if resolved.exists():
            try:
                data = json.loads(resolved.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                return f"错误：读取 notebook 失败: {exc}"
        else:
            data = {
                "cells": [],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }

        cells: list[dict] = data.setdefault("cells", [])
        new_cell = _new_cell(cell_type, new_source)

        if is_new_cell:
            insert_at = min(cell_idx, len(cells))
            cells.insert(insert_at, new_cell)
            action = f"已在索引 {insert_at} 插入新 cell"
        else:
            if cell_idx >= len(cells):
                return f"错误：cell_idx={cell_idx} 超出范围（共 {len(cells)} 个 cell）。"
            cells[cell_idx] = new_cell
            action = f"已更新 cell {cell_idx}"

        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(
                json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            return f"错误：写入 notebook 失败: {exc}"

        return f"{action}。文件: {ws.relative_display(resolved)}"
