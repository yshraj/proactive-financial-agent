"""Phase 3 — the conversation-restore endpoint.

Messages persist server-side; GET /api/chat/conversations/{id}/messages lets the
frontend re-render the visible thread after a reload/restart. Owner-scoped: a
conversation you don't own reads as empty, never another user's messages.
"""
from __future__ import annotations

from app.context import set_current_tenant
from app.services import conversations
from tests.conftest import auth_headers_for


def _seed_conversation(ctx):
    set_current_tenant(ctx)
    try:
        conv_id = conversations.create()
        conversations.add_message(conv_id, "user", "hello")
        conversations.add_message(conv_id, "assistant", "hi there")
        return conv_id
    finally:
        set_current_tenant(None)


def test_restores_persisted_thread(api_client, clean_db, org_a):
    conv_id = _seed_conversation(org_a)

    res = api_client.get(
        f"/api/chat/conversations/{conv_id}/messages", headers=auth_headers_for(org_a)
    )
    assert res.status_code == 200
    body = res.json()
    assert body["conversation_id"] == conv_id
    assert [(m["role"], m["content"]) for m in body["messages"]] == [
        ("user", "hello"),
        ("assistant", "hi there"),
    ]


def test_other_user_cannot_read_thread(api_client, clean_db, org_a, org_b):
    conv_id = _seed_conversation(org_a)
    # org_b owns nothing here: the endpoint returns an empty thread, not a leak.
    res = api_client.get(
        f"/api/chat/conversations/{conv_id}/messages", headers=auth_headers_for(org_b)
    )
    assert res.status_code == 200
    assert res.json()["messages"] == []


def test_unknown_conversation_is_empty_not_error(api_client, clean_db, org_a):
    res = api_client.get(
        "/api/chat/conversations/not-a-real-id/messages",
        headers=auth_headers_for(org_a),
    )
    assert res.status_code == 200
    assert res.json()["messages"] == []
