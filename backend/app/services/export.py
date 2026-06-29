"""
CSV export helpers.

Pure serialisation utilities (no DB or network) so they can be unit-tested in
isolation. Output follows RFC 4180: fields containing a comma, double quote, or
line break are wrapped in double quotes, and embedded double quotes are doubled.
"""
from __future__ import annotations

from typing import Any, Iterable, Sequence

# CRLF line terminator per RFC 4180 (Excel-friendly).
_LINE_TERMINATOR = "\r\n"


def _format_cell(value: Any) -> str:
    """Render a single value as a CSV-safe string."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    if any(ch in text for ch in (",", '"', "\n", "\r")):
        return '"' + text.replace('"', '""') + '"'
    return text


def rows_to_csv(
    rows: Iterable[dict[str, Any]],
    columns: Sequence[str],
    headers: Sequence[str] | None = None,
) -> str:
    """
    Serialise an iterable of row dicts into a CSV string.

    Args:
        rows: dict rows keyed by column name; missing keys render as empty.
        columns: ordered column keys to emit.
        headers: optional human-friendly header labels (defaults to ``columns``).

    Returns:
        CSV text with a header row, RFC 4180 quoting, and CRLF line endings.
    """
    if headers is not None and len(headers) != len(columns):
        raise ValueError("headers and columns must have the same length")

    label_row = list(headers) if headers is not None else list(columns)
    lines = [",".join(_format_cell(h) for h in label_row)]
    for row in rows:
        lines.append(",".join(_format_cell(row.get(col)) for col in columns))
    return _LINE_TERMINATOR.join(lines) + _LINE_TERMINATOR
