"""Tests for context compression and memory (layer 3)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from codeagent.agent import Agent
from codeagent.config import Settings
from codeagent.context.compressor import Compressor
from codeagent.context.errors import ContextOverflowError
from codeagent.context.tokens import count_request
from codeagent.conversation import Conversation
from codeagent.llm.base import ChatResult
from codeagent.memory.tiered import TieredMemory
from codeagent.prompts.manager import PromptManager
from codeagent.tools import build_default_registry


class FakeLLM:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, tools=None, on_text_delta=None):
        self.calls += 1
        user = messages[-1]["content"] if messages else ""
        if "工具输出原文" in user or "提炼为可继续执行任务" in user:
            return ChatResult(
                content=json.dumps(
                    ["测试失败：缺少 expiresAt 字段", "构建成功，无错误"],
                    ensure_ascii=False,
                ),
                raw_message={"role": "assistant", "content": "[]"},
            )
        if "会话压缩器" in user:
            return ChatResult(
                content=json.dumps(
                    {
                        "snapshot": "1. 目标：修 bug\n2. 进度：50%\n3. 文件：a.py",
                        "session_memory": ["- 正在修复 auth 模块"],
                        "workspace_memory": ["- workspace 进度"],
                        "workspace_long_term_new": ["- 使用 Python 3.11"],
                        "global_memory_new": ["- 始终用中文回复"],
                    },
                    ensure_ascii=False,
                ),
                raw_message={"role": "assistant", "content": "{}"},
            )
        return ChatResult(
            content="任务完成",
            raw_message={"role": "assistant", "content": "任务完成"},
        )


def _settings(workspace: Path, budget: int) -> Settings:
    root = workspace.parent
    return Settings(
        provider="deepseek",
        api_key="k",
        base_url="http://x",
        model="m",
        max_turns=4,
        subagent_max_turns=4,
        workspace=workspace,
        context_tokens=budget,
        sessions_dir=root / "sessions",
        global_memory_dir=root / "global_memory",
    )


def _memory(workspace: Path) -> TieredMemory:
    return TieredMemory(workspace, workspace.parent / "global_memory")


def test_stage1_distills_tool_outputs() -> None:
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        memory = _memory(ws)
        prompts = PromptManager(workspace=ws, memory=memory, global_memory_dir=ws.parent / "global_memory")
        llm = FakeLLM()
        budget = 1200
        compressor = Compressor(llm, budget=budget, prompts=prompts, memory=memory)
        conv = Conversation(prompts.full_system())
        conv.add_user("修 bug")
        long_log = "FAIL line output " * 200
        conv.add_assistant(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "Bash", "arguments": "{}"},
                    }
                ],
            }
        )
        conv.add_tool_result("c1", long_log, name="Bash")

        schemas = None
        assert compressor._stage1_tool_distill(conv) is True
        tools = [m for m in conv.to_messages() if m.get("role") == "tool"]
        assert len(tools) == 1
        assert "[已压缩]" in str(tools[0].get("content"))


def test_stage2_snapshot_and_memory() -> None:
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        memory = _memory(ws)
        prompts = PromptManager(workspace=ws, memory=memory, global_memory_dir=ws.parent / "global_memory")
        llm = FakeLLM()
        compressor = Compressor(llm, budget=2500, prompts=prompts, memory=memory)
        conv = Conversation(prompts.full_system())
        conv.add_user("大任务 " + ("x" * 400))
        conv.add_assistant({"role": "assistant", "content": "好的"})
        compressor._stage2_snapshot(conv)
        msgs = conv.to_messages()
        assert len(msgs) == 2
        assert msgs[1]["content"].startswith("[会话快照]")
        assert memory.session
        assert memory.workspace_store.read_long_term()
        assert memory.global_store.read()


def test_overflow_raises() -> None:
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        memory = _memory(ws)
        prompts = PromptManager(workspace=ws, memory=memory, global_memory_dir=ws.parent / "global_memory")

        class TinyLLM:
            def chat(self, messages, tools=None, on_text_delta=None):
                return ChatResult(content="x" * 5000, raw_message={})

        compressor = Compressor(TinyLLM(), budget=50, prompts=prompts, memory=memory)
        conv = Conversation(prompts.full_system())
        conv.add_user("y" * 5000)
        try:
            compressor.ensure_fits(conv, None)
            raise AssertionError("should overflow")
        except ContextOverflowError as exc:
            assert exc.budget == 50


def test_agent_with_fake_llm() -> None:
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        settings = _settings(ws, budget=100_000)
        agent = Agent.from_settings(settings, llm=FakeLLM())
        out = agent.run("你好")
        assert out == "任务完成"
        stats = agent.token_usage()
        assert stats["usage_tokens"] > 0
        assert stats["context_tokens"] > 0
        assert stats["context_budget"] == 100_000


if __name__ == "__main__":
    test_stage1_distills_tool_outputs()
    test_stage2_snapshot_and_memory()
    test_overflow_raises()
    test_agent_with_fake_llm()
    print("ALL OK")
