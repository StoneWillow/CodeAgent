from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WebInteraction:
    """Blocking callbacks for Bash confirm and AskUser on the Web UI."""

    on_pending: Any = None
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _event: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _pending: dict[str, Any] | None = field(default=None, init=False, repr=False)
    _result: str | bool = field(default=False, init=False, repr=False)

    def pending(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._pending) if self._pending else None

    def _wait(self, payload: dict[str, Any], timeout: float = 300.0) -> str | bool:
        with self._lock:
            self._pending = payload
            self._result = False
            self._event.clear()
        if self.on_pending is not None:
            self.on_pending(payload)
        if not self._event.wait(timeout=timeout):
            with self._lock:
                self._pending = None
            return False if payload.get("type") == "bash" else ""
        with self._lock:
            result = self._result
            self._pending = None
            return result

    def confirm_bash(self, command: str, reason: str) -> bool:
        result = self._wait(
            {"type": "bash", "command": command, "reason": reason},
            timeout=300.0,
        )
        return bool(result)

    def ask_user(
        self,
        question: str,
        options: list[str] | None,
        allow_multiple: bool,
    ) -> str:
        result = self._wait(
            {
                "type": "ask",
                "question": question,
                "options": options or [],
                "allow_multiple": allow_multiple,
            },
            timeout=600.0,
        )
        return str(result) if result is not False else ""

    def resolve(self, approved: bool | None = None, answer: str | None = None) -> bool:
        with self._lock:
            if self._pending is None:
                return False
            if self._pending.get("type") == "bash":
                self._result = bool(approved)
            else:
                self._result = answer or ""
            self._event.set()
            return True
