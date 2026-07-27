"""_parse_llm_json repair behaviour.

Providers in JSON mode still emit syntax slips; the production incident this
covers was gemini-2.5-flash returning a trailing comma mid-object — at
temperature 0 the same document produced the same broken JSON on every
retry, so extraction failed deterministically until the parser could repair
it. No DB, no network: pure unit tests.
"""
from __future__ import annotations

import json

import pytest

from app.services.llm_extractor import _parse_llm_json

VALID = {"client": {"full_name": "Margaret Whitfield"}, "alerts": []}


def test_plain_valid_json_passes_through():
    assert _parse_llm_json(json.dumps(VALID)) == VALID


def test_markdown_fence_is_tolerated():
    raw = "```json\n" + json.dumps(VALID) + "\n```"
    assert _parse_llm_json(raw) == VALID


def test_trailing_comma_in_object_is_repaired():
    raw = '{"client": {"full_name": "M. Whitfield", "risk_score": 5,}, "alerts": [],}'
    data = _parse_llm_json(raw)
    assert data["client"]["risk_score"] == 5
    assert data["alerts"] == []


def test_trailing_comma_in_array_is_repaired():
    raw = '{"alerts": [{"type": "DEADLINE"}, {"type": "FOLLOW_UP"},]}'
    assert [a["type"] for a in _parse_llm_json(raw)["alerts"]] == [
        "DEADLINE",
        "FOLLOW_UP",
    ]


def test_line_comment_is_repaired():
    raw = '{\n  "client": {"full_name": "M"}, // extracted from page 1\n  "alerts": []\n}'
    assert _parse_llm_json(raw)["client"]["full_name"] == "M"


def test_block_comment_and_trailing_comma_together():
    raw = '{\n  "client": {"full_name": "M"}, /* no alerts found */\n  "alerts": [],\n}'
    data = _parse_llm_json(raw)
    assert data["alerts"] == []


def test_slashes_inside_string_values_survive():
    raw = '{"client": {"raw_profile_json": "see https://example.com//path"}, "alerts": [,]}'
    # The URL's double slash must not be treated as a comment while the
    # parser repairs the stray comma in the alerts array.
    data = _parse_llm_json(raw)
    assert data["client"]["raw_profile_json"] == "see https://example.com//path"
    assert data["alerts"] == []


def test_slashes_inside_strings_with_repairable_slip():
    raw = '{"client": {"full_name": "A // B", "notes": "x, }"}, "alerts": [],}'
    data = _parse_llm_json(raw)
    assert data["client"]["full_name"] == "A // B"
    assert data["client"]["notes"] == "x, }"


def test_escaped_quote_inside_string_does_not_break_scanning():
    raw = '{"client": {"full_name": "M \\"Peg\\" W"}, "alerts": [],}'
    assert _parse_llm_json(raw)["client"]["full_name"] == 'M "Peg" W'


def test_unrepairable_json_raises_original_error():
    raw = '{"client": {"full_name": totally_unquoted}, "alerts": []}'
    with pytest.raises(json.JSONDecodeError) as exc_info:
        _parse_llm_json(raw)
    # The original error position is preserved for the log line.
    assert exc_info.value.pos > 0
