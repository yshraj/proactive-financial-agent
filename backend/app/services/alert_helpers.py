"""Shared alert query helpers and synthetic alert builders."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

REVIEW_OVERDUE_DESCRIPTION = (
    "No review in 12+ months. Consumer Duty requires demonstrating ongoing value."
)

ALERTS_WITH_CLIENT_SQL = """
    SELECT a.id, a.client_id, a.trigger_date, a.type, a.priority, a.title, a.description, a.status,
           c.full_name AS client_name
    FROM alerts a
    JOIN clients c ON c.id = a.client_id
"""


def alert_from_row(r: dict) -> dict[str, Any]:
    """Map a joined alerts+clients row to AlertOut-compatible dict."""
    return {
        "id": str(r["id"]),
        "client_id": str(r["client_id"]),
        "client_name": (r.get("client_name") or "Unknown").strip(),
        "trigger_date": r["trigger_date"].isoformat() if r.get("trigger_date") else "",
        "type": (r.get("type") or ""),
        "priority": (r.get("priority") or ""),
        "title": r.get("title"),
        "description": r.get("description"),
        "status": (r.get("status") or "PENDING"),
    }


def synthetic_review_overdue(
    client_id: str,
    client_name: str,
    trigger_date: date | str,
) -> dict[str, Any]:
    """Build a synthetic REVIEW_OVERDUE alert dict."""
    trigger_iso = trigger_date.isoformat() if isinstance(trigger_date, date) else trigger_date
    return {
        "id": f"review-overdue-{client_id}",
        "client_id": client_id,
        "client_name": client_name.strip(),
        "trigger_date": trigger_iso,
        "type": "REVIEW_OVERDUE",
        "priority": "HIGH",
        "title": "Annual review overdue",
        "description": REVIEW_OVERDUE_DESCRIPTION,
        "status": "PENDING",
    }


def alert_sort_key(alert: Any) -> tuple:
    """Sort by trigger_date then priority (HIGH first)."""
    priority_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(getattr(alert, "priority", alert.get("priority")), 2)
    trigger = getattr(alert, "trigger_date", alert.get("trigger_date", ""))
    return (trigger, priority_rank)


def get_client_name(client_id: str, default: str = "Client") -> str:
    from app.db import get_cursor

    with get_cursor() as cur:
        cur.execute("SELECT full_name FROM clients WHERE id = %s", (client_id,))
        row = cur.fetchone()
    if not row:
        return default
    return (row.get("full_name") or default).strip()


def require_client_name(client_id: str) -> str:
    """Return client display name or raise LookupError if the client does not exist."""
    from app.db import get_cursor

    with get_cursor() as cur:
        cur.execute("SELECT full_name FROM clients WHERE id = %s", (client_id,))
        row = cur.fetchone()
    if not row:
        raise LookupError("Client not found")
    return (row.get("full_name") or "Client").strip()
