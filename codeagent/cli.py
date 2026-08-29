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


def _print_tool(name: str, arguments: dict[str, Any]) -> None:
    args = arguments or {}
    print(f"  [工具] {name}({args})", flush=True)


def _reply(agent: Agent, user_text: str) -> None:
    print("Agent> ", end="", flush=True)
    output = agent.run(user_text)
    print(output, flush=True)


def main(argv: list[str] | None = None) -> None:
    _configure_stdio()
    args = sys.argv[1:] if argv is None else argv

    settings = load_settings()
    if not settings.api_key:
        print("缺少 API key。请复制 .env.example 为 .env 并填写 DEEPSEEK_API_KEY。")
        sys.exit(1)

    try:
        agent = Agent.from_settings(settings, on_tool=_print_tool)
    except ValueError as exc:
        print(str(exc))
        sys.exit(1)

    print(
        f"CodeAgent  |  provider={settings.provider}  model={settings.model}\n"
        f"工作区: {settings.workspace}\n"
        "同一会话内多轮对话；输入 exit 退出。\n"
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
