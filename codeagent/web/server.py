from __future__ import annotations

import json
import mimetypes
import re
import threading
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from codeagent.agent import Agent
from codeagent.config import load_settings
from codeagent.context.errors import ContextOverflowError
from codeagent.context.tokens import count_messages
from codeagent.llm.errors import ContextLengthAPIError, LLMRequestError
from codeagent.sessions.helpers import build_agent_for_session, persist_session
from codeagent.sessions.store import SessionRecord, SessionStore
from codeagent.tools import TodoStore
from codeagent.web.interaction import WebInteraction

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

CHAT_LOCK = threading.Lock()


class _AppState:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.store = SessionStore(self.settings.sessions_dir)
        self.interaction = WebInteraction()
        self._agents: dict[str, Agent] = {}
        self._todos: dict[str, TodoStore] = {}

    def get_or_create_agent(self, session: SessionRecord) -> tuple[Agent, TodoStore]:
        if session.id in self._agents:
            return self._agents[session.id], self._todos[session.id]
        agent, todo_store = build_agent_for_session(
            self.settings,
            session,
            ask_user=self.interaction.ask_user,
            confirm_bash=self.interaction.confirm_bash,
        )
        self._agents[session.id] = agent
        self._todos[session.id] = todo_store
        return agent, todo_store

    def drop_agent(self, session_id: str) -> None:
        self._agents.pop(session_id, None)
        self._todos.pop(session_id, None)


STATE = _AppState()


def _token_payload(record: SessionRecord) -> dict[str, int]:
    agent = STATE._agents.get(record.id)
    if agent is not None:
        return agent.token_usage()
    context = record.context_tokens
    if not context and record.messages:
        context = count_messages(record.messages)
    return {
        "context_tokens": context,
        "usage_tokens": record.usage_tokens,
        "context_budget": STATE.settings.context_tokens,
    }


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(length) if length else b"{}"
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _public_messages(session: SessionRecord) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for msg in session.messages:
        role = msg.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = str(msg.get("content") or "").strip()
        if not content or content.startswith("[会话快照]"):
            continue
        items.append({"role": role, "content": content})
    return items


def _sse_write(handler: BaseHTTPRequestHandler, event: str, data: Any) -> None:
    payload = json.dumps(data, ensure_ascii=False)
    chunk = f"event: {event}\ndata: {payload}\n\n".encode("utf-8")
    handler.wfile.write(chunk)
    handler.wfile.flush()


class WebHandler(BaseHTTPRequestHandler):
    server_version = "CodeAgentWeb/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path in {"/", "/index.html"}:
            self._serve_static("index.html")
            return

        if path == "/api/sessions":
            items = [
                {
                    "id": s.id,
                    "title": s.title,
                    "updated_at": s.updated_at,
                }
                for s in STATE.store.list()
            ]
            _json_response(self, HTTPStatus.OK, {"sessions": items})
            return

        if path == "/api/sessions/search":
            query = parse_qs(parsed.query).get("q", [""])[0]
            hits = [
                {
                    "id": s.id,
                    "title": s.title,
                    "updated_at": s.updated_at,
                    "snippet": s.snippet,
                }
                for s in STATE.store.search(query)
            ]
            _json_response(self, HTTPStatus.OK, {"sessions": hits})
            return

        match = re.fullmatch(r"/api/sessions/([^/]+)", path)
        if match:
            session_id = match.group(1)
            record = STATE.store.load(session_id)
            if record is None:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "id": record.id,
                    "title": record.title,
                    "updated_at": record.updated_at,
                    "messages": _public_messages(record),
                    **_token_payload(record),
                },
            )
            return

        if path.startswith("/static/"):
            self._serve_static(path[len("/static/") :])
            return

        _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        match = re.fullmatch(r"/api/sessions/([^/]+)", parsed.path)
        if not match:
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        session_id = match.group(1)
        STATE.drop_agent(session_id)
        if not STATE.store.delete(session_id):
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        _json_response(self, HTTPStatus.OK, {"ok": True, "id": session_id})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/sessions":
            record = STATE.store.create()
            _json_response(
                self,
                HTTPStatus.CREATED,
                {
                    "id": record.id,
                    "title": record.title,
                    "updated_at": record.updated_at,
                    "messages": [],
                    **_token_payload(record),
                },
            )
            return

        if path == "/api/confirm":
            data = _read_json(self)
            pending = STATE.interaction.pending()
            if pending is None:
                _json_response(self, HTTPStatus.CONFLICT, {"error": "no_pending"})
                return
            if pending.get("type") == "bash":
                ok = STATE.interaction.resolve(approved=bool(data.get("approved")))
            else:
                ok = STATE.interaction.resolve(answer=str(data.get("answer") or ""))
            _json_response(self, HTTPStatus.OK, {"ok": ok})
            return

        if path == "/api/chat":
            self._handle_chat()
            return

        _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def _serve_static(self, name: str) -> None:
        file_path = (STATIC_DIR / name).resolve()
        if not str(file_path).startswith(str(STATIC_DIR.resolve())):
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not file_path.exists() or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = file_path.read_bytes()
        mime, _ = mimetypes.guess_type(str(file_path))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _handle_chat(self) -> None:
        data = _read_json(self)
        session_id = str(data.get("session_id") or "").strip()
        message = str(data.get("message") or "").strip()
        if not session_id or not message:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "invalid_body"})
            return

        record = STATE.store.load(session_id)
        if record is None:
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "session_not_found"})
            return

        if not STATE.settings.api_key:
            _json_response(self, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "missing_api_key"})
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        if not CHAT_LOCK.acquire(blocking=False):
            _sse_write(self, "error", {"message": "另一个对话正在处理，请稍候"})
            _sse_write(self, "done", {})
            return

        try:
            def emit_pending(payload: dict[str, Any]) -> None:
                _sse_write(self, "confirm", payload)

            STATE.interaction.on_pending = emit_pending
            agent, todo_store = STATE.get_or_create_agent(record)

            def on_text(delta: str) -> None:
                if delta:
                    _sse_write(self, "token", {"text": delta})

            def on_tool(name: str, arguments: dict[str, Any]) -> None:
                _sse_write(self, "tool", {"name": name, "arguments": arguments})

            def on_compress(msg: str) -> None:
                if msg:
                    _sse_write(self, "compress", {"message": msg})

            try:
                output = agent.run(
                    message,
                    on_text_delta=on_text,
                    on_tool=on_tool,
                    on_compress=on_compress,
                )
            except ContextOverflowError as exc:
                _sse_write(
                    self,
                    "error",
                    {"message": f"上下文超过上限 ({exc.used}/{exc.budget} token)"},
                )
                _sse_write(self, "done", {})
                return
            except ContextLengthAPIError as exc:
                _sse_write(self, "error", {"message": f"模型拒绝过长上下文: {exc}"})
                _sse_write(self, "done", {})
                return
            except LLMRequestError as exc:
                _sse_write(self, "error", {"message": str(exc)})
                _sse_write(self, "done", {})
                return
            except Exception:
                _sse_write(self, "error", {"message": traceback.format_exc()})
                _sse_write(self, "done", {})
                return

            persist_session(STATE.store, record, agent, todo_store)
            _sse_write(self, "done", {"text": output, **_token_payload(record)})
        finally:
            STATE.interaction.on_pending = None
            CHAT_LOCK.release()


def run_web_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    if not STATE.settings.api_key:
        print("缺少 API key。请复制 .env.example 为 .env 并填写 DEEPSEEK_API_KEY。")
        raise SystemExit(1)

    server = ThreadingHTTPServer((host, port), WebHandler)
    url = f"http://{host}:{port}"
    print(f"CodeAgent Web  |  {url}")
    print(f"工作区: {STATE.settings.workspace}")
    print(f"会话目录: {STATE.settings.sessions_dir}")
    print("按 Ctrl+C 停止服务")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.server_close()
