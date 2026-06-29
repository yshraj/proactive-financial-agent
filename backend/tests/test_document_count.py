"""Tests for the Client 360 document-count helper and its graceful degradation."""
from __future__ import annotations

import psycopg2

from app.routers.monitor import _document_count_for_client


class _FakeCursor:
    """Minimal cursor stub returning a fixed count."""

    def __init__(self, count):
        self._count = count

    def execute(self, sql, params=None):  # noqa: D401 - stub
        self._sql = sql

    def fetchone(self):
        return {"n": self._count}


class _MissingColumnCursor:
    """Cursor stub that raises as if the client_id column is absent."""

    def execute(self, sql, params=None):
        raise psycopg2.errors.UndefinedColumn("column does not exist")

    def fetchone(self):  # pragma: no cover - never reached
        return None


def test_counts_documents():
    assert _document_count_for_client(_FakeCursor(3), "c1") == 3


def test_zero_when_no_rows():
    assert _document_count_for_client(_FakeCursor(0), "c1") == 0


def test_handles_null_count():
    assert _document_count_for_client(_FakeCursor(None), "c1") == 0


def test_returns_zero_when_column_missing():
    # Migration 002 not applied: should not raise, just report 0.
    assert _document_count_for_client(_MissingColumnCursor(), "c1") == 0
