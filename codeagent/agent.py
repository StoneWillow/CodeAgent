from __future__ import annotations

from typing import Any, Callable

from codeagent.config import Settings
from codeagent.conversation import Conversation
from codeagent.llm.base import LLMClient, TextDeltaListener
from codeagent.llm.factory import create_llm
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
        max_turns: int,
        on_tool: ToolListener | None = None,
        on_text_delta: TextDeltaListener | None = None,
    ) -> None:
        self._llm = llm
        self._conversation = conversation
        self._prompts = prompts
        self._tools = tools
        self._max_turns = max_turns
        self._on_tool = on_tool
        self._on_text_delta = on_text_delta

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        on_tool: ToolListener | None = None,
        on_text_delta: TextDeltaListener | None = None,
        tools: ToolRegistry | None = None,
        prompts: PromptManager | None = None,
        llm: LLMClient | None = None,
        ask_user: AskUser | None = None,
        confirm_bash: ConfirmBash | None = None,
        todo_store: TodoStore | None = None,
    ) -> Agent:
        prompts = prompts or PromptManager(workspace=settings.workspace)
        return cls(
            llm=llm or create_llm(settings),
            conversation=Conversation(prompts.system_prompt),
            prompts=prompts,
            tools=tools
            or build_default_registry(
                settings.workspace,
                ask_user=ask_user,
                confirm_bash=confirm_bash,
                todo_store=todo_store,
            ),
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

        for _ in range(self._max_turns):
            result = self._llm.chat(
                self._messages_for_llm(),
                tools=schemas or None,
                on_text_delta=text_cb,
            )
            self._conversation.add_assistant(result.raw_message)

            if not result.has_tool_calls:
                text = (result.content or "").strip()
                return text or "(模型没有返回文本)"

            for call in result.tool_calls:
                if tool_cb is not None:
                    tool_cb(call.name, call.arguments)
                observation = self._tools.execute(call.name, call.arguments)
                self._conversation.add_tool_result(
                    tool_call_id=call.id,
                    content=observation,
                    name=call.name,
                )

        return "已达到本轮最大循环次数，停止。"

    def _messages_for_llm(self) -> list[dict[str, Any]]:
        messages = self._conversation.to_messages()
        extra = self._prompts.extra_messages()
        if not extra:
            return messages
        return [messages[0], *extra, *messages[1:]]
