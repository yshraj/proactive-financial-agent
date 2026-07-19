"""Tests for transcript ingestion helpers (no DB/LLM required)."""
from __future__ import annotations

from app.routers.ingest import doc_type_for_ext
from app.services.llm_extractor import extract_structured_from_text


def test_doc_type_for_ext():
    assert doc_type_for_ext(".pdf") == ("PDF", "pdf")
    assert doc_type_for_ext(".docx") == ("Word", "docx")
    assert doc_type_for_ext(".md") == ("Markdown", "markdown")
    assert doc_type_for_ext(".txt") == ("Transcript", "transcript")
    assert doc_type_for_ext(".odt") == ("Document", "document")


def test_short_text_returns_placeholder_without_llm():
    # Under 50 chars short-circuits before any LLM call.
    result = extract_structured_from_text("too short")
    assert result["client"]["full_name"] == "Unknown Client"
    assert result["alerts"] == []
    assert result["raw_text"] == "too short"


def test_empty_text_returns_placeholder():
    result = extract_structured_from_text("")
    assert result["client"]["full_name"] == "Unknown Client"
    assert result["raw_text"] == ""
