from __future__ import annotations

from autopapers.agents.messages import Message


def test_message_meta_not_shared_between_instances() -> None:
    a = Message(type="info", content="a")
    b = Message(type="info", content="b")
    a.meta["k"] = 1
    assert b.meta == {}


def test_message_fields() -> None:
    m = Message(type="warning", content="hello", meta={"x": 2})
    assert m.type == "warning"
    assert m.content == "hello"
    assert m.meta == {"x": 2}
    assert m.created_at  # ISO timestamp from factory
