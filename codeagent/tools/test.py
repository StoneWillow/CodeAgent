from __future__ import annotations

from typing import Any

from codeagent.tools.base import Tool


class TestTool(Tool):
    name = "test"
    description = (
        "最小测试工具。当用户要求验证工具调用、测试工具，或明确让你调用 test 时使用。"
        "无需参数。"
    )
    parameters = {
        "type": "object",
        "properties": {},
    }

    def execute(self, arguments: dict[str, Any]) -> str:
        return "你调用了工具"
