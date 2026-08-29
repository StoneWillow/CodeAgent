from __future__ import annotations

import json
import tempfile
from pathlib import Path

from codeagent.config import Settings
from codeagent.llm.base import ChatResult, ToolCall
from codeagent.tools import build_default_registry, build_explore_registry
from codeagent.tools.subagent import _agent_depth


def test_explore_registry_readonly() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "ws"
        root.mkdir()
        (root / "a.py").write_text("print('hi')\n", encoding="utf-8")
        reg = build_explore_registry(root)
        names = {s["function"]["name"] for s in reg.schemas()}
        assert names == {"Glob", "Grep", "Read"}
        assert "[error:unknown_tool]" in reg.execute("Write", {"path": "x.py", "contents": "bad"})
        assert "[error:unknown_tool]" in reg.execute("Task", {"prompt": "x"})


def test_task_path_out_of_bounds() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "ws"
        root.mkdir()
        settings = Settings(
            provider="deepseek",
            api_key="k",
            base_url="http://x",
            model="m",
            max_turns=4,
            subagent_max_turns=4,
            workspace=root,
            context_tokens=100_000,
            sessions_dir=Path(td) / "sessions",
            global_memory_dir=Path(td) / "global_memory",
        )
        reg = build_default_registry(root, settings=settings, include_task=True)
        out = reg.execute("Task", {"prompt": "find files", "path": ".."})
        assert "越界" in out


def test_task_runs_subagent_and_returns_summary() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "ws"
        root.mkdir()
        (root / "auth.py").write_text("def login():\n    pass\n", encoding="utf-8")

        class SubLLM:
            def __init__(self) -> None:
                self.calls = 0

            def chat(self, messages, tools=None, on_text_delta=None):
                self.calls += 1
                last = messages[-1]
                if last.get("role") == "user":
                    content = str(last.get("content") or "")
                    if "探索" in content or "login" in content:
                        return ChatResult(
                            content=None,
                            tool_calls=[
                                ToolCall(
                                    id="c1",
                                    name="Grep",
                                    arguments={"pattern": "login", "path": "."},
                                )
                            ],
                            raw_message={
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "c1",
                                        "type": "function",
                                        "function": {
                                            "name": "Grep",
                                            "arguments": json.dumps(
                                                {"pattern": "login", "path": "."},
                                                ensure_ascii=False,
                                            ),
                                        },
                                    }
                                ],
                            },
                        )
                return ChatResult(
                    content="摘要：auth.py 含 login 函数。",
                    raw_message={
                        "role": "assistant",
                        "content": "摘要：auth.py 含 login 函数。",
                    },
                )

        settings = Settings(
            provider="deepseek",
            api_key="k",
            base_url="http://x",
            model="m",
            max_turns=4,
            subagent_max_turns=4,
            workspace=root,
            context_tokens=100_000,
            sessions_dir=Path(td) / "sessions",
            global_memory_dir=Path(td) / "global_memory",
        )

        llm = SubLLM()
        reg = build_default_registry(root, settings=settings, include_task=True, llm=llm)
        out = reg.execute(
            "Task",
            {"prompt": "探索 login 相关代码", "path": "."},
        )
        assert "auth.py" in out
        assert "login" in out.lower() or "摘要" in out
        assert llm.calls >= 2


def test_task_denied_when_nested_depth() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "ws"
        root.mkdir()
        settings = Settings(
            provider="deepseek",
            api_key="k",
            base_url="http://x",
            model="m",
            max_turns=4,
            subagent_max_turns=4,
            workspace=root,
            context_tokens=100_000,
            sessions_dir=Path(td) / "sessions",
            global_memory_dir=Path(td) / "global_memory",
        )
        reg = build_default_registry(root, settings=settings, include_task=True)
        token = _agent_depth.set(1)
        try:
            out = reg.execute("Task", {"prompt": "nested"})
            assert "[error:denied]" in out
        finally:
            _agent_depth.reset(token)


def test_default_registry_includes_task() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "ws"
        root.mkdir()
        settings = Settings(
            provider="deepseek",
            api_key="k",
            base_url="http://x",
            model="m",
            max_turns=4,
            subagent_max_turns=4,
            workspace=root,
            context_tokens=100_000,
            sessions_dir=Path(td) / "sessions",
            global_memory_dir=Path(td) / "global_memory",
        )
        reg = build_default_registry(root, settings=settings)
        names = {s["function"]["name"] for s in reg.schemas()}
        assert "Task" in names
