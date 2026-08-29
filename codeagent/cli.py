from __future__ import annotations

import sys
from typing import Any

from codeagent.agent import Agent
from codeagent.config import load_settings


def _configure_stdio() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
            sys.stdin.reconfigure(encoding="utf-8")
        except Exception:
            pass


class _StreamPrinter:
    """Print tokens as they arrive; tool lines on their own row."""

    def __init__(self) -> None:
        self.saw_text = False
        self._in_text = False

    def on_text(self, delta: str) -> None:
        if not delta:
            return
        if not self._in_text:
            print("Agent> ", end="", flush=True)
            self._in_text = True
            self.saw_text = True
        print(delta, end="", flush=True)

    def on_tool(self, name: str, arguments: dict[str, Any]) -> None:
        if self._in_text:
            print(flush=True)
            self._in_text = False
        print(f"  [工具] {name}({arguments or {}})", flush=True)

    def finish(self, fallback: str | None = None) -> None:
        if self._in_text:
            print(flush=True)
            self._in_text = False
        elif fallback:
            print(f"Agent> {fallback}", flush=True)


def _cli_confirm_bash(command: str, reason: str) -> bool:
    print(f"\n[权限确认] Bash 命令需要用户批准")
    print(f"  原因: {reason}")
    print(f"  命令: {command}")
    try:
        answer = input("  允许执行? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in {"y", "yes"}


def _cli_ask_user(
    question: str,
    options: list[str] | None,
    allow_multiple: bool,
) -> str:
    print(f"\n[向用户提问] {question}")
    if not options:
        try:
            return input("  你的回答: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return ""

    for idx, opt in enumerate(options, start=1):
        print(f"  {idx}. {opt}")
    hint = "输入编号（多选用逗号分隔）" if allow_multiple else "输入编号"
    try:
        raw = input(f"  {hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""

    if allow_multiple:
        picks: list[str] = []
        for part in raw.replace("，", ",").split(","):
            part = part.strip()
            if not part.isdigit():
                continue
            i = int(part) - 1
            if 0 <= i < len(options):
                picks.append(options[i])
        return ", ".join(picks) if picks else raw
    if raw.isdigit():
        i = int(raw) - 1
        if 0 <= i < len(options):
            return options[i]
    return raw


def _reply(agent: Agent, user_text: str) -> None:
    printer = _StreamPrinter()
    output = agent.run(
        user_text,
        on_text_delta=printer.on_text,
        on_tool=printer.on_tool,
    )
    printer.finish(fallback=None if printer.saw_text else output)


def main(argv: list[str] | None = None) -> None:
    _configure_stdio()
    args = sys.argv[1:] if argv is None else argv

    settings = load_settings()
    if not settings.api_key:
        print("缺少 API key。请复制 .env.example 为 .env 并填写 DEEPSEEK_API_KEY。")
        sys.exit(1)

    try:
        agent = Agent.from_settings(
            settings,
            ask_user=_cli_ask_user,
            confirm_bash=_cli_confirm_bash,
        )
    except ValueError as exc:
        print(str(exc))
        sys.exit(1)

    print(
        f"CodeAgent  |  provider={settings.provider}  model={settings.model}\n"
        f"工作区: {settings.workspace}\n"
        "同一会话内多轮对话；回复为流式输出。输入 exit 退出。\n"
    )

    first = " ".join(args).strip()
    if first:
        print(f"你> {first}")
        _reply(agent, first)

    while True:
        try:
            line = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.lower() in {"exit", "quit", "/exit", "/quit"}:
            break
        _reply(agent, line)


if __name__ == "__main__":
    main()
