"""Tests for adviser note templates."""
from __future__ import annotations

import pytest

from app.services.note_templates import (
    NOTE_TEMPLATES,
    list_templates,
    render_template,
)


def test_list_templates_metadata():
    items = list_templates()
    assert len(items) == len(NOTE_TEMPLATES)
    for item in items:
        assert item["id"] in NOTE_TEMPLATES
        assert item["section_count"] >= 1
        assert item["name"]


def test_render_includes_title_and_section_headings():
    md = render_template("annual_review")
    assert md.startswith("# Annual review")
    for section in NOTE_TEMPLATES["annual_review"]["sections"]:
        assert f"## {section}" in md


def test_render_unknown_raises():
    with pytest.raises(KeyError):
        render_template("nope")


def test_all_templates_render():
    for tid in NOTE_TEMPLATES:
        md = render_template(tid)
        assert md.strip().startswith("#")
