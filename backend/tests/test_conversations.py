"""Tests for in-memory conversation memory."""
from __future__ import annotations

import pytest

from app.services import conversations


@pytest.fixture(autouse=True)
def _clear():
    conversations.clear()
    yield
    conversations.clear()


def test_create_returns_unique_ids():
    a = conversations.create()
    b = conversations.create()
    assert a and b and a != b
    assert conversations.exists(a)


def test_add_and_get_messages_in_order():
    conv = conversations.create()
    conversations.add_message(conv, "user", "hi")
    conversations.add_message(conv, "assistant", "hello")
    msgs = conversations.get_messages(conv)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"] == "hi"


def test_add_message_autocreates_conversation():
    conversations.add_message("new-conv", "user", "x")
    assert conversations.exists("new-conv")


def test_window_caps_messages():
    conv = conversations.create()
    for i in range(30):
        conversations.add_message(conv, "user", str(i))
    msgs = conversations.get_messages(conv)
    assert len(msgs) <= 20
    assert msgs[-1]["content"] == "29"


def test_format_history_renders_roles():
    history = conversations.format_history(
        [{"role": "user", "content": "What's overdue?"}, {"role": "assistant", "content": "Two reviews."}]
    )
    assert "Adviser: What's overdue?" in history
    assert "Jarvis: Two reviews." in history


def test_format_history_empty():
    assert conversations.format_history([]) == ""


def test_format_history_truncates_to_recent():
    msgs = [{"role": "user", "content": "x" * 100} for _ in range(100)]
    out = conversations.format_history(msgs, max_chars=500)
    assert len(out) <= 501  # leading ellipsis + 500
    assert out.startswith("…")


def test_clear_removes_all():
    conv = conversations.create()
    conversations.add_message(conv, "user", "x")
    conversations.clear()
    assert not conversations.exists(conv)
