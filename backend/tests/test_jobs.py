"""Tests for the in-memory background-job registry."""
from __future__ import annotations

import pytest

from app.services import jobs


@pytest.fixture(autouse=True)
def _clear():
    jobs.clear()
    yield
    jobs.clear()


def test_create_starts_pending():
    job = jobs.create("j1", kind="upload", filename="a.pdf")
    assert job["status"] == jobs.PENDING
    assert job["progress"] == 0
    assert job["filename"] == "a.pdf"


def test_update_patches_fields():
    jobs.create("j1", kind="upload")
    updated = jobs.update("j1", status=jobs.DONE, progress=100, document_id="d1")
    assert updated["status"] == jobs.DONE
    assert updated["progress"] == 100
    assert updated["document_id"] == "d1"


def test_update_unknown_returns_none():
    assert jobs.update("nope", status=jobs.DONE) is None


def test_get_returns_copy_not_reference():
    jobs.create("j1", kind="upload")
    a = jobs.get("j1")
    a["status"] = "MUTATED"
    assert jobs.get("j1")["status"] == jobs.PENDING


def test_get_unknown_returns_none():
    assert jobs.get("missing") is None


def test_clear_empties_registry():
    jobs.create("j1", kind="upload")
    jobs.clear()
    assert jobs.get("j1") is None
