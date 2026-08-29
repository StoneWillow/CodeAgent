from __future__ import annotations

import json
import tempfile
from pathlib import Path

from codeagent.memory.tiered import TieredMemory
from codeagent.prompts.manager import PromptManager
from codeagent.sessions.helpers import build_agent_for_session, persist_session
from codeagent.sessions.store import SessionStore


def test_tiered_memory_prompt_sections() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws = root / "ws"
        ws.mkdir()
        global_dir = root / "global_memory"
        memory = TieredMemory(ws, global_dir, session_rules=["- 本会话：修 calculator"])
        memory.merge_global(["- 全局：用中文"])
        memory.write_workspace_short(["- 工作区：pytest 测试"])
        memory.merge_workspace_long(["- 工作区长期：Python 3.11"])

        prompts = PromptManager(workspace=ws, memory=memory, global_memory_dir=global_dir)
        system = prompts.full_system()
        assert "# 全局记忆" in system
        assert "# 工作区记忆" in system
        assert "# 会话记忆" in system
        assert "本会话：修 calculator" in system


def test_session_memory_persisted() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws = root / "ws"
        ws.mkdir()
        from codeagent.config import Settings

        settings = Settings(
            provider="deepseek",
            api_key="k",
            base_url="http://x",
            model="m",
            max_turns=4,
            workspace=ws,
            context_tokens=100_000,
            sessions_dir=root / "sessions",
            global_memory_dir=root / "global_memory",
        )
        store = SessionStore(settings.sessions_dir)
        session = store.create()
        session.memory = ["- 进度：50%"]
        store.save(session)

        agent, todos = build_agent_for_session(settings, session)
        assert agent.memory.session == ["- 进度：50%"]

        agent.memory.write_session(["- 进度：80%"])
        persist_session(store, session, agent, todos)

        loaded = store.load(session.id)
        assert loaded is not None
        assert loaded.memory == ["- 进度：80%"]
