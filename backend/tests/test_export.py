"""Tests for the CSV export serialiser (RFC 4180 quoting)."""
from __future__ import annotations

from app.services.export import rows_to_csv


def test_header_only_when_no_rows():
    csv = rows_to_csv([], ["a", "b"], ["A", "B"])
    assert csv == "A,B\r\n"


def test_defaults_headers_to_columns():
    csv = rows_to_csv([], ["a", "b"])
    assert csv == "a,b\r\n"


def test_basic_rows_and_missing_keys():
    rows = [{"a": 1, "b": "x"}, {"a": 2}]  # second row missing "b"
    csv = rows_to_csv(rows, ["a", "b"])
    assert csv == "a,b\r\n1,x\r\n2,\r\n"


def test_quotes_fields_with_comma_quote_or_newline():
    rows = [{"v": "a,b"}, {"v": 'he said "hi"'}, {"v": "line1\nline2"}]
    csv = rows_to_csv(rows, ["v"])
    lines = csv.split("\r\n")
    assert lines[0] == "v"
    assert lines[1] == '"a,b"'
    assert lines[2] == '"he said ""hi"""'
    # newline-containing field stays quoted (the literal \n is inside the quotes)
    assert '"line1\nline2"' in csv


def test_none_renders_empty_and_bool_lowercased():
    csv = rows_to_csv([{"a": None, "b": True, "c": False}], ["a", "b", "c"])
    assert csv == "a,b,c\r\n,true,false\r\n"


def test_mismatched_headers_length_raises():
    try:
        rows_to_csv([], ["a", "b"], ["only-one"])
    except ValueError:
        return
    raise AssertionError("expected ValueError for mismatched headers")
