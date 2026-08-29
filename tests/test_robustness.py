"""Robustness: validation, circuit breaker, truncation, compress fallback."""

from __future__ import annotations

import tempfile
from pathlib import Path

from codeagent.agent import Agent
from codeagent.config import Settings
from codeagent.context.compressor import Compressor
from codeagent.conversation import Conversation
from codeagent.llm.base import ChatResult
from codeagent.llm.errors import ContextLengthAPIError
from codeagent.memory.tiered import TieredMemory
from codeagent.prompts.manager import PromptManager
from codeagent.tools import build_default_registry
from codeagent.tools.errors import is_error_observation


def test_missing_required_arg() -> None:
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        reg = build_default_registry(ws)
        out = reg.execute("Read", {})
        assert "[error:invalid_args]" in out
        assert "path" in out


def test_circuit_breaker() -> None:
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        reg = build_default_registry(ws)
        for _ in range(3):
            out = reg.execute("Read", {})
            assert "[error:invalid_args]" in out
        blocked = reg.execute("Read", {})
        assert "[error:circuit]" in blocked


def test_truncate_long_output() -> None:
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        huge = "abcdefghij" * 20000
        (ws / "big.txt").write_text(huge, encoding="utf-8")
        reg = build_default_registry(ws)
        out = reg.execute("Read", {"path": "big.txt"})
        assert "已截断" in out


def test_compress_llm_failure_falls_back() -> None:
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        memory = TieredMemory(ws, Path(td) / "global_memory")
        prompts = PromptManager(workspace=ws, memory=memory, global_memory_dir=Path(td) / "global_memory")

        class BoomLLM:
            def chat(self, messages, tools=None, on_text_delta=None):
                raise RuntimeError("compress down")

        compressor = Compressor(BoomLLM(), budget=1200, prompts=prompts, memory=memory)
        conv = Conversation(prompts.full_system())
        conv.add_user("修")
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
        conv.add_tool_result("c1", "FAIL line output " * 200, name="Bash")
        assert compressor._stage1_tool_distill(conv) is True
        tool_msg = [m for m in conv.to_messages() if m.get("role") == "tool"][0]
        assert "[已压缩]" in tool_msg["content"]


def test_api_context_overflow_forces_snapshot() -> None:
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        ws.mkdir()

        class FlakyLLM:
            def __init__(self) -> None:
                self.n = 0

            def chat(self, messages, tools=None, on_text_delta=None):
                user = (messages[-1].get("content") or "") if messages else ""
                system = (messages[0].get("content") or "") if messages else ""
                if "JSON" in system or "压缩" in user:
                    return ChatResult(
                        content='{"snapshot":"目标：写函数","session_memory":["- 正在写函数"],"workspace_memory":[],"workspace_long_term_new":[],"global_memory_new":[]}',
                        raw_message={"role": "assistant", "content": "{}"},
                    )
                self.n += 1
                if self.n == 1:
                    raise ContextLengthAPIError("context_length_exceeded")
                return ChatResult(
                    content="好的继续",
                    raw_message={"role": "assistant", "content": "好的继续"},
                )

        settings = Settings(
            provider="deepseek",
            api_key="k",
            base_url="http://x",
            model="m",
            max_turns=4,
            workspace=ws,
            context_tokens=100_000,
            sessions_dir=ws.parent / "sessions",
            global_memory_dir=ws.parent / "global_memory",
        )
        llm = FlakyLLM()
        agent = Agent.from_settings(settings, llm=llm)
        out = agent.run("写一个函数")
        assert out == "好的继续"
        assert llm.n == 2
        msgs = agent.conversation.to_messages()
        assert any("[会话快照]" in str(m.get("content") or "") for m in msgs)


def test_unknown_tool_is_error() -> None:
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        ws.mkdir()
        reg = build_default_registry(ws)
        out = reg.execute("NoSuch", {})
        assert is_error_observation(out)
        assert "unknown_tool" in out


if __name__ == "__main__":
    test_missing_required_arg()
    test_circuit_breaker()
    test_truncate_long_output()
    test_compress_llm_failure_falls_back()
    test_api_context_overflow_forces_snapshot()
    test_unknown_tool_is_error()
    print("ALL OK")
