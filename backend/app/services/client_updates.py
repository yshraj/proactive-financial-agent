"""
Validation/coercion for manual client-record edits.

Pure functions (no DB) so they can be unit-tested. Mirrors the coercion rules
used during ingestion (risk score 1-10, non-negative money, ISO review date)
but rejects invalid input with a clear message rather than silently dropping it,
because a human edit should fail loudly.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

# Columns a user may edit, in a stable order for predictable SQL.
EDITABLE_FIELDS = (
    "full_name",
    "retirement_target_age",
    "risk_score",
    "total_assets",
    "cash_savings",
    "last_review_date",
)


def _coerce_int(value: Any, field: str) -> int:
    if isinstance(value, bool):  # bool is a subclass of int; reject it explicitly
        raise ValueError(f"{field} must be a number.")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a whole number.") from None


def _coerce_money(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number.")
    try:
        amount = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number.") from None
    if amount < 0:
        raise ValueError(f"{field} cannot be negative.")
    return amount


def validate_client_update(provided: dict[str, Any]) -> dict[str, Any]:
    """
    Validate and coerce a partial client update.

    Args:
        provided: fields the caller explicitly set (already excludes unset).

    Returns:
        A dict of cleaned column -> value, ready for a parameterised UPDATE.
        Values may be ``None`` to clear an optional field.

    Raises:
        ValueError: if no editable field is present or any value is invalid.
    """
    cleaned: dict[str, Any] = {}

    for field in EDITABLE_FIELDS:
        if field not in provided:
            continue
        value = provided[field]

        if field == "full_name":
            if value is None or not str(value).strip():
                raise ValueError("Name cannot be empty.")
            cleaned[field] = str(value).strip()[:200]

        elif field == "retirement_target_age":
            if value is None:
                cleaned[field] = None
            else:
                age = _coerce_int(value, "Retirement target age")
                if age < 30 or age > 120:
                    raise ValueError("Retirement target age must be between 30 and 120.")
                cleaned[field] = age

        elif field == "risk_score":
            if value is None:
                cleaned[field] = None
            else:
                score = _coerce_int(value, "Risk score")
                if score < 1 or score > 10:
                    raise ValueError("Risk score must be between 1 and 10.")
                cleaned[field] = score

        elif field in ("total_assets", "cash_savings"):
            label = "Total assets" if field == "total_assets" else "Cash savings"
            cleaned[field] = None if value is None else _coerce_money(value, label)

        elif field == "last_review_date":
            if value is None or not str(value).strip():
                cleaned[field] = None
            else:
                text = str(value).strip()
                try:
                    datetime.strptime(text, "%Y-%m-%d")
                except ValueError:
                    raise ValueError("Last review date must be in YYYY-MM-DD format.") from None
                cleaned[field] = text

    if not cleaned:
        raise ValueError("No editable fields provided.")
    return cleaned
