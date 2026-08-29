from __future__ import annotations

from typing import Any, Callable

from codeagent.agent import Agent
from codeagent.config import Settings
from codeagent.conversation import Conversation
from codeagent.context.compressor import CompressionListener
from codeagent.llm.base import TextDeltaListener
from codeagent.sessions.store import SessionRecord, SessionStore
from codeagent.tools import AskUser, ConfirmBash, TodoStore

ToolListener = Callable[[str, dict[str, Any]], None]


def build_agent_for_session(
    settings: Settings,
    session: SessionRecord,
    *,
    todo_store: TodoStore | None = None,
    ask_user: AskUser | None = None,
    confirm_bash: ConfirmBash | None = None,
    on_tool: ToolListener | None = None,
    on_text_delta: TextDeltaListener | None = None,
    on_compress: CompressionListener | None = None,
) -> tuple[Agent, TodoStore]:
    store = todo_store or TodoStore()
    if session.todos:
        store.load_list(session.todos)
    conversation: Conversation | None = None
    if session.messages:
        conversation = Conversation.from_dict({"messages": session.messages})
    agent = Agent.from_settings(
        settings,
        conversation=conversation,
        todo_store=store,
        session_memory=session.memory,
        ask_user=ask_user,
        confirm_bash=confirm_bash,
        on_tool=on_tool,
        on_text_delta=on_text_delta,
        on_compress=on_compress,
        usage_tokens=session.usage_tokens,
    )
    return agent, store


def persist_session(
    store: SessionStore,
    session: SessionRecord,
    agent: Agent,
    todo_store: TodoStore,
) -> None:
    session.messages = agent.conversation.to_dict()["messages"]
    session.todos = todo_store.to_list()
    session.memory = list(agent.memory.session)
    stats = agent.token_usage()
    session.usage_tokens = stats["usage_tokens"]
    session.context_tokens = stats["context_tokens"]
    store.save(session)
