"""Durable conversation memory: persistence, windowing, and ownership."""
from __future__ import annotations

from app.services import conversations


def test_create_returns_unique_ids(bind_org_a):
    a = conversations.create()
    b = conversations.create()
    assert a and b and a != b
    assert conversations.exists(a)


def test_add_and_get_messages_in_order(bind_org_a):
    conv = conversations.create()
    conversations.add_message(conv, "user", "hi")
    conversations.add_message(conv, "assistant", "hello")
    msgs = conversations.get_messages(conv)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"] == "hi"


def test_unknown_conversation_does_not_exist(bind_org_a):
    assert conversations.exists("not-a-uuid") is False
    assert conversations.get_messages("not-a-uuid") == []


def test_window_caps_messages(bind_org_a):
    conv = conversations.create()
    for i in range(30):
        conversations.add_message(conv, "user", str(i))
    msgs = conversations.get_messages(conv)
    assert len(msgs) <= 20
    assert msgs[-1]["content"] == "29"


def test_conversations_survive_reconnect(bind_org_a, clean_db):
    from app.db import close_pool

    conv = conversations.create()
    conversations.add_message(conv, "user", "remember me")
    close_pool()  # simulate process restart
    assert conversations.exists(conv)
    assert conversations.get_messages(conv)[0]["content"] == "remember me"


def test_conversation_hijack_is_closed(clean_db, org_a, org_b):
    """Another user/org cannot see, continue, or write to a conversation."""
    conv = conversations.create(ctx=org_a)
    conversations.add_message(conv, "user", "org A secret", ctx=org_a)

    assert conversations.exists(conv, ctx=org_b) is False
    assert conversations.get_messages(conv, ctx=org_b) == []
    # Writing into someone else's thread is a silent no-op.
    conversations.add_message(conv, "user", "intruder", ctx=org_b)
    contents = [m["content"] for m in conversations.get_messages(conv, ctx=org_a)]
    assert "intruder" not in contents


def test_clear_removes_org_threads_only(clean_db, org_a, org_b):
    conv_a = conversations.create(ctx=org_a)
    conv_b = conversations.create(ctx=org_b)
    conversations.clear(ctx=org_a)
    assert conversations.exists(conv_a, ctx=org_a) is False
    assert conversations.exists(conv_b, ctx=org_b) is True


# ---------------------------------------------------------------------------
# Pure helpers (no DB)
# ---------------------------------------------------------------------------


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
