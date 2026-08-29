from __future__ import annotations

import uuid
from typing import Any, Callable

from codeagent.config import Settings
from codeagent.context.compressor import Compressor, CompressionListener
from codeagent.conversation import Conversation
from codeagent.llm.base import LLMClient, TextDeltaListener
from codeagent.llm.errors import ContextLengthAPIError, LLMRequestError
from codeagent.llm.factory import create_llm
from codeagent.memory.store import MemoryStore
from codeagent.prompts.manager import PromptManager
from codeagent.tools import AskUser, ConfirmBash, TodoStore, build_default_registry
from codeagent.tools.registry import ToolRegistry

ToolListener = Callable[[str, dict[str, Any]], None]


class Agent:
    """ReAct loop: model -> optional local tools -> model ... until a user-facing reply."""

    def __init__(
        self,
        llm: LLMClient,
        conversation: Conversation,
        prompts: PromptManager,
        tools: ToolRegistry,
        compressor: Compressor,
        max_turns: int,
        on_tool: ToolListener | None = None,
        on_text_delta: TextDeltaListener | None = None,
    ) -> None:
        self._llm = llm
        self._conversation = conversation
        self._prompts = prompts
        self._tools = tools
        self._compressor = compressor
        self._max_turns = max_turns
        self._on_tool = on_tool
        self._on_text_delta = on_text_delta

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        on_tool: ToolListener | None = None,
        on_text_delta: TextDeltaListener | None = None,
        on_compress: CompressionListener | None = None,
        tools: ToolRegistry | None = None,
        prompts: PromptManager | None = None,
        llm: LLMClient | None = None,
        ask_user: AskUser | None = None,
        confirm_bash: ConfirmBash | None = None,
        todo_store: TodoStore | None = None,
        memory: MemoryStore | None = None,
        compressor: Compressor | None = None,
        conversation: Conversation | None = None,
    ) -> Agent:
        memory = memory or MemoryStore(settings.workspace)
        prompts = prompts or PromptManager(workspace=settings.workspace, memory=memory)
        llm_client = llm or create_llm(settings)
        compressor = compressor or Compressor(
            llm=llm_client,
            budget=settings.context_tokens,
            prompts=prompts,
            memory=memory,
            on_compress=on_compress,
        )
        return cls(
            llm=llm_client,
            conversation=conversation or Conversation(prompts.full_system()),
            prompts=prompts,
            tools=tools
            or build_default_registry(
                settings.workspace,
                ask_user=ask_user,
                confirm_bash=confirm_bash,
                todo_store=todo_store,
            ),
            compressor=compressor,
            max_turns=settings.max_turns,
            on_tool=on_tool,
            on_text_delta=on_text_delta,
        )

    @property
    def conversation(self) -> Conversation:
        return self._conversation

    def run(
        self,
        user_text: str,
        on_text_delta: TextDeltaListener | None = None,
        on_tool: ToolListener | None = None,
    ) -> str:
        self._conversation.add_user(user_text)
        schemas = self._tools.schemas()
        text_cb = on_text_delta or self._on_text_delta
        tool_cb = on_tool or self._on_tool
        last_observation = ""
        forced_snapshot = False

        for _ in range(self._max_turns):
            messages = self._compressor.ensure_fits(self._conversation, schemas)
            try:
                result = self._llm.chat(
                    messages,
                    tools=schemas or None,
                    on_text_delta=text_cb,
                )
            except ContextLengthAPIError:
                if forced_snapshot:
                    raise
                self._compressor.force_snapshot(self._conversation)
                forced_snapshot = True
                continue
            except LLMRequestError as exc:
                return f"模型请求失败: {exc}"

            self._conversation.add_assistant(result.raw_message)

            if not result.has_tool_calls:
                text = (result.content or "").strip()
                return text or "(模型没有返回文本)"

            for call in result.tool_calls:
                if not call.id:
                    call.id = f"call_{uuid.uuid4().hex[:8]}"
                if tool_cb is not None:
                    tool_cb(call.name, call.arguments)
                observation = self._tools.execute(call.name, call.arguments)
                last_observation = observation
                self._conversation.add_tool_result(
                    tool_call_id=call.id,
                    content=observation,
                    name=call.name,
                )

        suffix = f"\n最后一次工具观察: {last_observation[:500]}" if last_observation else ""
        return "已达到本轮最大循环次数，停止。" + suffix
