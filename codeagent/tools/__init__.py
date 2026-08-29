from __future__ import annotations

from pathlib import Path

from codeagent.tools.base import Tool
from codeagent.tools.decorator import FunctionTool, tool
from codeagent.tools.files import register_file_tools
from codeagent.tools.registry import ToolRegistry
from codeagent.tools.test import TestTool
from codeagent.tools.workspace import Workspace


def build_default_registry(workspace: Path) -> ToolRegistry:
    ws = Workspace(workspace)
    registry = ToolRegistry()
    register_file_tools(registry, ws)
    registry.register(TestTool())
    return registry


__all__ = [
    "Tool",
    "FunctionTool",
    "ToolRegistry",
    "TestTool",
    "Workspace",
    "tool",
    "build_default_registry",
]
