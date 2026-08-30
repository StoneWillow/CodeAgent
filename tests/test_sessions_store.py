from __future__ import annotations

import json
from pathlib import Path

import pytest

from codeagent.conversation import Conversation
from codeagent.sessions.store import SessionRecord, SessionStore


@pytest.fixture()
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "sessions")


def test_create_save_load(store: SessionStore) -> None:
    record = store.create()
    assert record.id
    assert record.title == "新对话"

    conv = Conversation("system")
    conv.add_user("帮我写一个快速排序")
    conv.add_assistant({"role": "assistant", "content": "好的，我来写。"})
    record.messages = conv.to_dict()["messages"]
    store.save(record)

    loaded = store.load(record.id)
    assert loaded is not None
    assert loaded.title == "帮我写一个快速排序"
    assert len(loaded.messages) == 3
    assert loaded.messages[1]["content"] == "帮我写一个快速排序"


def test_list_order(store: SessionStore) -> None:
    a = store.create()
    b = store.create()
    a.title = "会话 A"
    b.title = "会话 B"
    store.save(a)
    store.save(b)

    items = store.list()
    assert [s.id for s in items] == [b.id, a.id]


def test_search_title_and_content(store: SessionStore) -> None:
    record = store.create()
    conv = Conversation("system")
    conv.add_user("实现二叉树遍历")
    conv.add_assistant({"role": "assistant", "content": "使用前序遍历示例。"})
    record.messages = conv.to_dict()["messages"]
    store.save(record)

    by_title = store.search("二叉树")
    assert len(by_title) == 1
    assert by_title[0].id == record.id
    assert "二叉树" in by_title[0].snippet or "二叉树" in by_title[0].title

    by_content = store.search("前序")
    assert len(by_content) == 1
    assert by_content[0].snippet


def test_load_missing(store: SessionStore) -> None:
    assert store.load("missing") is None


def test_corrupt_file_ignored(store: SessionStore) -> None:
    path = store.root / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    assert store.load("bad") is None
    assert store.list() == []


def test_persist_roundtrip_with_todos(store: SessionStore) -> None:
    record = store.create()
    record.todos = [
        {"id": "t1", "content": "写测试", "status": "in_progress"},
        {"id": "t2", "content": "写文档", "status": "pending"},
    ]
    store.save(record)

    raw = json.loads((store.root / f"{record.id}.json").read_text(encoding="utf-8"))
    assert raw["todos"][0]["status"] == "in_progress"


def test_token_fields_roundtrip(store: SessionStore) -> None:
    record = store.create()
    record.usage_tokens = 1234
    record.context_tokens = 56
    store.save(record)

    loaded = store.load(record.id)
    assert loaded is not None
    assert loaded.usage_tokens == 1234
    assert loaded.context_tokens == 56


def test_delete_session(store: SessionStore) -> None:
    record = store.create()
    assert store.load(record.id) is not None
    assert store.delete(record.id) is True
    assert store.load(record.id) is None
    assert store.delete(record.id) is False
    assert store.delete("../escape") is False
