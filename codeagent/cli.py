from __future__ import annotations

import argparse
import sys
from typing import Any

from codeagent.agent import Agent
from codeagent.config import Settings, load_settings
from codeagent.context.errors import ContextOverflowError
from codeagent.llm.errors import ContextLengthAPIError, LLMRequestError
from codeagent.sessions.helpers import build_agent_for_session, persist_session
from codeagent.sessions.store import SessionRecord, SessionStore
from codeagent.tools import TodoStore


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


class CliSessionManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = SessionStore(settings.sessions_dir)
        self.session = self.store.create()
        self.todo_store = TodoStore()
        self.agent = self._build_agent()

    def _build_agent(self) -> Agent:
        agent, todo_store = build_agent_for_session(
            self.settings,
            self.session,
            todo_store=self.todo_store,
            ask_user=_cli_ask_user,
            confirm_bash=_cli_confirm_bash,
            on_compress=lambda msg: print(msg, flush=True),
        )
        self.todo_store = todo_store
        return agent

    def save(self) -> None:
        persist_session(self.store, self.session, self.agent, self.todo_store)

    def new_session(self) -> SessionRecord:
        self.save()
        self.session = self.store.create()
        self.todo_store = TodoStore()
        self.agent = self._build_agent()
        return self.session

    def resume(self, session_id: str) -> bool:
        record = self.store.load(session_id)
        if record is None:
            return False
        self.session = record
        self.agent = self._build_agent()
        return True

    def list_sessions(self) -> None:
        items = self.store.list()
        if not items:
            print("(暂无已保存会话)")
            return
        print("最近会话:")
        for item in items:
            print(f"  {item.id}  {item.title}  ({item.updated_at})")

    def search_sessions(self, query: str) -> None:
        hits = self.store.search(query)
        if not hits:
            print(f"(未找到包含「{query}」的会话)")
            return
        print(f"检索「{query}」:")
        for item in hits:
            line = f"  {item.id}  {item.title}"
            if item.snippet:
                line += f"\n    …{item.snippet}…"
            print(line)

    def reply(self, user_text: str) -> None:
        printer = _StreamPrinter()
        try:
            output = self.agent.run(
                user_text,
                on_text_delta=printer.on_text,
                on_tool=printer.on_tool,
            )
        except ContextOverflowError as exc:
            print(f"\n错误：上下文超过上限 ({exc.used}/{exc.budget} token)，已停止。")
            sys.exit(1)
        except ContextLengthAPIError as exc:
            print(f"\n错误：模型拒绝过长上下文，压缩后仍失败。{exc}")
            sys.exit(1)
        except LLMRequestError as exc:
            print(f"\n错误：{exc}")
            sys.exit(1)
        printer.finish(fallback=None if printer.saw_text else output)
        self.save()

    def handle_slash(self, line: str) -> bool:
        parts = line.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "/new":
            session = self.new_session()
            print(f"已新建会话 {session.id}")
            return True
        if cmd == "/list":
            self.list_sessions()
            return True
        if cmd == "/resume":
            if not arg:
                print("用法: /resume <会话id>")
                return True
            if self.resume(arg):
                print(f"已恢复会话 {arg} ({self.session.title})")
            else:
                print(f"未找到会话: {arg}")
            return True
        if cmd == "/search":
            if not arg:
                print("用法: /search <关键词>")
                return True
            self.search_sessions(arg)
            return True
        if cmd == "/web":
            print("请使用: python -m codeagent --web")
            return True
        return False


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="codeagent")
    parser.add_argument("--web", action="store_true", help="启动本地 Web 界面")
    parser.add_argument("--resume", metavar="ID", help="恢复指定会话")
    parser.add_argument("message", nargs="*", help="首条用户消息")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    _configure_stdio()
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    if args.web:
        from codeagent.web.server import run_web_server

        run_web_server()
        return

    settings = load_settings()
    if not settings.api_key:
        print("缺少 API key。请复制 .env.example 为 .env 并填写 DEEPSEEK_API_KEY。")
        sys.exit(1)

    try:
        manager = CliSessionManager(settings)
    except ValueError as exc:
        print(str(exc))
        sys.exit(1)

    if args.resume:
        if not manager.resume(args.resume):
            print(f"未找到会话: {args.resume}")
            sys.exit(1)
        print(f"已恢复会话 {args.resume} ({manager.session.title})")

    print(
        f"CodeAgent  |  provider={settings.provider}  model={settings.model}\n"
        f"工作区: {settings.workspace}\n"
        f"会话: {manager.session.id}  |  目录: {settings.sessions_dir}\n"
        "同一会话内多轮对话；回复为流式输出。输入 exit 退出。\n"
        "斜杠命令: /new /list /resume <id> /search <词> /web\n"
    )

    first = " ".join(args.message).strip()
    if first:
        print(f"你> {first}")
        manager.reply(first)

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
        if line.startswith("/"):
            manager.handle_slash(line)
            continue
        manager.reply(line)


if __name__ == "__main__":
    main()
