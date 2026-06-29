"""Tests for the deterministic client review-note fallback."""
from __future__ import annotations

from app.services.review_note import fallback_review_note


def test_includes_client_name_and_date():
    note = fallback_review_note(
        client_name="Alan & Lynne Partridge",
        profile_bits="last review 2024-01-01, assets 895000",
        open_items=["Annual review overdue", "ISA top-up (due 2026-07-10)"],
        today_iso="2026-06-29",
    )
    assert "Alan & Lynne Partridge" in note
    assert "2026-06-29" in note
    assert "confirm before filing" in note.lower()


def test_lists_open_items():
    note = fallback_review_note(
        client_name="Test Client",
        profile_bits="assets 100000",
        open_items=["Item A", "Item B"],
        today_iso="2026-06-29",
    )
    assert "- Item A" in note
    assert "- Item B" in note


def test_handles_no_open_items():
    note = fallback_review_note(
        client_name="Test Client",
        profile_bits="",
        open_items=[],
        today_iso="2026-06-29",
    )
    assert "None outstanding" in note
    assert "No profile data on file." in note


def test_has_consumer_duty_section():
    note = fallback_review_note(
        client_name="Test Client",
        profile_bits="x",
        open_items=[],
        today_iso="2026-06-29",
    )
    assert "## Consumer Duty" in note
    assert "Vulnerability considerations" in note
