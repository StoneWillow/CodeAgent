from __future__ import annotations

import json
import re
from typing import Any, Callable

from codeagent.context.errors import ContextOverflowError
from codeagent.context.tokens import count_request, count_text_tokens
from codeagent.conversation import Conversation
from codeagent.llm.base import LLMClient
from codeagent.memory.tiered import TieredMemory
from codeagent.prompts.manager import PromptManager

CompressionListener = Callable[[str], None]

_STAGE1_THRESHOLD = 0.70
_STAGE2_THRESHOLD = 0.35
_MIN_TOOL_TOKENS = 200
_TRUNCATE_CHARS = 400
_COMPRESSED_PREFIX = "[已压缩] "

_STAGE1_PROMPT = """你是上下文压缩器。下面是一组工具输出原文。请提炼为可继续执行任务的状态摘要，不要保留日志原文。

要求：
- 返回 JSON 数组，长度必须与输入条数相同
- 每项是一句话状态，例如："auth.spec.ts 中 refresh token 用例失败，原因是 mock 缺少 expiresAt"
- 禁止贴堆栈、禁止复述大段输出

输入（JSON 数组，每项含 index 与 text）：
{payload}

只返回 JSON 数组，不要 markdown。"""

_STAGE2_PROMPT = """你是会话压缩器。把以下对话压成可继续执行的状态，并提取记忆规则。

返回 JSON（不要 markdown）：
{{
  "snapshot": "按七段写：1.用户目标与限制 2.任务进度 3.关键文件 4.已确认事实与决策 5.已排除路径 6.未完成与下一步 7.风险",
  "session_memory": ["- 本会话目标与进度，最多10条"],
  "workspace_memory": ["- 本工作区项目状态，最多10条"],
  "workspace_long_term_new": ["- 仅新增的工作区级长期规则，可为空"],
  "global_memory_new": ["- 仅新增的全局偏好/规则，可为空"]
}}

对话：
{payload}"""


def _extract_json_array(text: str) -> list[Any] | None:
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            return None
    return None


def _extract_json_object(text: str) -> dict[str, Any] | None:
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            return None
    return None


def _truncate_fallback(text: str) -> str:
    if len(text) <= _TRUNCATE_CHARS:
        return _COMPRESSED_PREFIX + text
    return _COMPRESSED_PREFIX + text[:_TRUNCATE_CHARS] + "...(已截断)"


class Compressor:
    def __init__(
        self,
        llm: LLMClient,
        budget: int,
        prompts: PromptManager,
        memory: TieredMemory,
        on_compress: CompressionListener | None = None,
    ) -> None:
        self._llm = llm
        self._budget = budget
        self._prompts = prompts
        self._memory = memory
        self._on_compress = on_compress

    @property
    def budget(self) -> int:
        return self._budget

    def ensure_fits(
        self,
        conversation: Conversation,
        tools: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        self._prompts.refresh_system()
        conversation.set_system(self._prompts.full_system())

        messages = conversation.to_messages()
        used = count_request(messages, tools)

        if used > self._budget:
            self._maybe_compress(conversation, tools, force_stage2=True)
            messages = conversation.to_messages()
            used = count_request(messages, tools)
            if used > self._budget:
                raise ContextOverflowError(used, self._budget)
            return messages

        if used >= int(self._budget * _STAGE1_THRESHOLD):
            self._maybe_compress(conversation, tools, force_stage2=False)
            messages = conversation.to_messages()
            used = count_request(messages, tools)

        if used > self._budget:
            raise ContextOverflowError(used, self._budget)

        return messages

    def force_snapshot(self, conversation: Conversation) -> None:
        """Used when the API still reports context overflow after local counting."""
        self._maybe_compress(conversation, tools=None, force_stage2=True)

    def _notify(self, msg: str) -> None:
        if self._on_compress is not None:
            self._on_compress(msg)

    def _maybe_compress(
        self,
        conversation: Conversation,
        tools: list[dict[str, Any]] | None,
        *,
        force_stage2: bool,
    ) -> None:
        messages = conversation.to_messages()
        used = count_request(messages, tools)

        if used >= int(self._budget * _STAGE1_THRESHOLD) or force_stage2:
            if self._stage1_tool_distill(conversation):
                self._notify("[上下文] 第一层工具蒸馏")
            self._prompts.refresh_system()
            conversation.set_system(self._prompts.full_system())

        messages = conversation.to_messages()
        used = count_request(messages, tools)

        need_stage2 = force_stage2 or used > int(self._budget * _STAGE2_THRESHOLD)
        if need_stage2:
            self._stage2_snapshot(conversation)
            self._notify("[上下文] 第二层会话快照")
            self._prompts.refresh_system()
            conversation.set_system(self._prompts.full_system())

    def _stage1_tool_distill(self, conversation: Conversation) -> bool:
        indices: list[int] = []
        payloads: list[dict[str, Any]] = []
        messages = conversation._messages

        for idx, msg in enumerate(messages):
            if msg.get("role") != "tool":
                continue
            text = str(msg.get("content") or "")
            if text.startswith(_COMPRESSED_PREFIX):
                continue
            if count_text_tokens(text) < _MIN_TOOL_TOKENS:
                continue
            indices.append(idx)
            payloads.append({"index": len(indices) - 1, "text": text[:8000]})

        if not indices:
            return False

        prompt = _STAGE1_PROMPT.format(payload=json.dumps(payloads, ensure_ascii=False))
        try:
            result = self._llm.chat(
                [
                    {"role": "system", "content": "你只输出 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                tools=None,
                on_text_delta=None,
            )
            summaries = _extract_json_array(result.content or "")
        except Exception:
            summaries = None
        if summaries is None or len(summaries) != len(indices):
            for i, idx in enumerate(indices):
                original = str(messages[idx].get("content") or "")
                messages[idx]["content"] = _truncate_fallback(original)
            return True

        for i, idx in enumerate(indices):
            summary = str(summaries[i]).strip()
            if not summary:
                original = str(messages[idx].get("content") or "")
                messages[idx]["content"] = _truncate_fallback(original)
            else:
                messages[idx]["content"] = _COMPRESSED_PREFIX + summary
        return True

    def _stage2_snapshot(self, conversation: Conversation) -> None:
        payload = json.dumps(conversation.to_messages()[1:], ensure_ascii=False)[:50000]
        prompt = _STAGE2_PROMPT.format(payload=payload)
        try:
            result = self._llm.chat(
                [
                    {"role": "system", "content": "你只输出 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                tools=None,
                on_text_delta=None,
            )
            data = _extract_json_object(result.content or "")
        except Exception:
            data = None
        snapshot = ""
        session_memory: list[str] = []
        workspace_memory: list[str] = []
        workspace_long_new: list[str] = []
        global_new: list[str] = []

        if data:
            snapshot = str(data.get("snapshot") or "").strip()
            sm = data.get("session_memory") or data.get("short_term") or []
            wm = data.get("workspace_memory") or []
            wl = data.get("workspace_long_term_new") or data.get("long_term_new") or []
            gn = data.get("global_memory_new") or []
            if isinstance(sm, list):
                session_memory = [str(x) for x in sm]
            if isinstance(wm, list):
                workspace_memory = [str(x) for x in wm]
            if isinstance(wl, list):
                workspace_long_new = [str(x) for x in wl]
            if isinstance(gn, list):
                global_new = [str(x) for x in gn]

        if not snapshot:
            snapshot = self._fallback_snapshot(conversation)

        if session_memory:
            self._memory.write_session(session_memory)
        if workspace_memory:
            self._memory.write_workspace_short(workspace_memory)
        if workspace_long_new:
            self._memory.merge_workspace_long(workspace_long_new)
        if global_new:
            self._memory.merge_global(global_new)

        conversation.replace_with_snapshot(self._prompts.full_system(), snapshot)

    def _fallback_snapshot(self, conversation: Conversation) -> str:
        lines = ["（自动截断快照）"]
        for msg in conversation.to_messages()[1:]:
            role = msg.get("role", "?")
            content = str(msg.get("content") or "")[:500]
            lines.append(f"[{role}] {content}")
        return "\n".join(lines)
