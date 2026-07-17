"""Durable audit: review register (ai_outputs) + append-only audit_log."""
from __future__ import annotations

import psycopg2
import pytest

from app.services import audit


def test_record_and_recent_newest_first(bind_org_a):
    audit.record(kind="review_note", output="First")
    audit.record(kind="draft_email", output="Second")
    entries = audit.recent()
    assert [e["kind"] for e in entries] == ["draft_email", "review_note"]
    assert entries[0]["id"] > entries[1]["id"]


def test_preview_is_truncated_and_single_line(bind_org_a):
    long = "line one\n" + ("x" * 300)
    entry = audit.record(kind="digest", output=long)
    assert "\n" not in entry["preview"]
    assert entry["preview"].endswith("…")
    assert len(entry["preview"]) <= 161


def test_limit_and_offset_are_respected(bind_org_a):
    for i in range(5):
        audit.record(kind="k", output=str(i))
    assert len(audit.recent(limit=3)) == 3
    page_two = audit.recent(limit=3, offset=3)
    assert len(page_two) == 2


def test_clear_empties_the_register_but_not_the_log(bind_org_a):
    audit.record(kind="k", output="x")
    assert audit.recent() != []
    audit.clear()
    assert audit.recent() == []
    # The immutable event log keeps the generation events.
    actions = [e["action"] for e in audit.events()]
    assert "ai.k.generated" in actions


def test_new_entries_start_unreviewed(bind_org_a):
    entry = audit.record(kind="review_note", output="x")
    assert entry["reviewed"] is False
    assert entry["reviewed_at"] is None


def test_approve_marks_reviewed_and_writes_event(bind_org_a):
    entry = audit.record(kind="review_note", output="x")
    updated = audit.approve(entry["id"])
    assert updated["reviewed"] is True
    assert updated["reviewed_at"]
    # Persisted: a fresh read reflects the approval.
    assert audit.recent()[0]["reviewed"] is True
    actions = [e["action"] for e in audit.events()]
    assert "ai.output.approved" in actions


def test_approve_unknown_returns_none(bind_org_a):
    assert audit.approve(99999) is None


def test_records_metadata(bind_org_a, clean_db, org_a):
    from tests.conftest import seed_client

    client_id = seed_client(clean_db, org_a.org_id, "Alan Partridge")
    entry = audit.record(
        kind="review_note",
        client_id=client_id,
        client_name="Alan",
        model="gpt-4o-mini",
        output="note",
        ai_generated=False,
    )
    assert entry["client_id"] == client_id
    assert entry["client_name"] == "Alan"
    assert entry["model"] == "gpt-4o-mini"
    assert entry["ai_generated"] is False


def test_survives_reconnect(bind_org_a, clean_db):
    """The whole point: audit entries live in Postgres, not process memory."""
    from app.db import close_pool

    audit.record(kind="digest", output="persisted")
    close_pool()  # simulate a process restart dropping all in-memory state
    assert audit.recent()[0]["preview"] == "persisted"


def test_event_log_is_append_only_for_runtime_role(bind_org_a, clean_db):
    """UPDATE/DELETE on audit_log must fail for the app role (grants + trigger)."""
    audit.record_event(action="client.updated", resource_type="client", resource_id="x")
    from app.db import get_cursor

    with pytest.raises(psycopg2.Error):
        with get_cursor(commit=True) as cur:
            cur.execute("UPDATE audit_log SET action = 'tampered'")
    with pytest.raises(psycopg2.Error):
        with get_cursor(commit=True) as cur:
            cur.execute("DELETE FROM audit_log")


def test_events_are_org_scoped(clean_db, org_a, org_b):
    audit.record_event(action="client.updated", ctx=org_a)
    audit.record_event(action="data.exported", ctx=org_b)
    a_actions = [e["action"] for e in audit.events(ctx=org_a)]
    b_actions = [e["action"] for e in audit.events(ctx=org_b)]
    assert a_actions == ["client.updated"]
    assert b_actions == ["data.exported"]


def test_record_without_context_fails_softly():
    # No tenant bound and required=False: returns None instead of raising.
    assert audit.record(kind="digest", output="x") is None
    assert audit.record_event(action="x.y") is None


def test_required_event_without_context_raises():
    with pytest.raises(RuntimeError):
        audit.record_event(action="data.cleared", required=True)
