from codeagent.tools.base import Tool
from codeagent.tools.registry import ToolRegistry
from codeagent.tools.test import TestTool


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(TestTool())
    return registry


__all__ = ["Tool", "ToolRegistry", "TestTool", "build_default_registry"]
