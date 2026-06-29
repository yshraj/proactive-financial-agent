"""
Book-level analytics.

Pure aggregation over client rows (no DB/LLM) so it is fully unit-testable.
The monitor router fetches the rows and delegates the maths here.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

REVIEW_OVERDUE_DAYS = 365


def compute_book_analytics(clients: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """
    Aggregate headline metrics for the whole client book.

    Args:
        clients: rows with optional ``total_assets``, ``risk_score`` and
            ``last_review_date`` (a ``date`` or ``None``).
        today: reference date for the review-overdue cutoff.

    Returns:
        ``{clients_total, total_aum, average_risk_score, reviews_overdue}``.
        ``average_risk_score`` is ``None`` when no client has a risk score.
    """
    total = len(clients)
    total_aum = sum(
        float(c["total_assets"]) for c in clients if c.get("total_assets") is not None
    )
    risks = [c["risk_score"] for c in clients if c.get("risk_score") is not None]
    average_risk_score: Optional[float] = (
        round(sum(risks) / len(risks), 1) if risks else None
    )

    cutoff = today - timedelta(days=REVIEW_OVERDUE_DAYS)

    def _is_overdue(client: dict[str, Any]) -> bool:
        last_review = client.get("last_review_date")
        return last_review is None or last_review < cutoff

    reviews_overdue = sum(1 for c in clients if _is_overdue(c))

    return {
        "clients_total": total,
        "total_aum": total_aum,
        "average_risk_score": average_risk_score,
        "reviews_overdue": reviews_overdue,
    }
