"""Tests for the in-memory AI audit log."""
from __future__ import annotations

import pytest

from app.services import audit


@pytest.fixture(autouse=True)
def _clear_audit():
    audit.clear()
    yield
    audit.clear()


def test_record_and_recent_newest_first():
    audit.record(kind="review_note", timestamp="2026-06-29T10:00:00", output="First")
    audit.record(kind="draft_email", timestamp="2026-06-29T10:01:00", output="Second")
    entries = audit.recent()
    assert [e["kind"] for e in entries] == ["draft_email", "review_note"]
    assert entries[0]["id"] > entries[1]["id"]


def test_preview_is_truncated_and_single_line():
    long = "line one\n" + ("x" * 300)
    entry = audit.record(kind="digest", timestamp="t", output=long)
    assert "\n" not in entry["preview"]
    assert entry["preview"].endswith("…")
    assert len(entry["preview"]) <= 161


def test_limit_is_respected():
    for i in range(5):
        audit.record(kind="k", timestamp=str(i), output=str(i))
    assert len(audit.recent(limit=3)) == 3


def test_clear_empties_the_log():
    audit.record(kind="k", timestamp="t", output="x")
    audit.clear()
    assert audit.recent() == []


def test_new_entries_start_unreviewed():
    entry = audit.record(kind="review_note", timestamp="t", output="x")
    assert entry["reviewed"] is False
    assert entry["reviewed_at"] is None


def test_approve_marks_reviewed():
    entry = audit.record(kind="review_note", timestamp="t", output="x")
    updated = audit.approve(entry["id"], "2026-06-29T12:00:00")
    assert updated["reviewed"] is True
    assert updated["reviewed_at"] == "2026-06-29T12:00:00"
    # Persisted: a fresh read reflects the approval.
    assert audit.recent()[0]["reviewed"] is True


def test_approve_unknown_returns_none():
    assert audit.approve(99999, "t") is None


def test_records_metadata():
    entry = audit.record(
        kind="review_note",
        timestamp="t",
        client_id="c1",
        client_name="Alan",
        model="gpt-4o-mini",
        output="note",
        ai_generated=False,
    )
    assert entry["client_id"] == "c1"
    assert entry["client_name"] == "Alan"
    assert entry["model"] == "gpt-4o-mini"
    assert entry["ai_generated"] is False
