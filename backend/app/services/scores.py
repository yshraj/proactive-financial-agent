"""
Deterministic client-intelligence scores and next-best-action ranking.

Pure functions (no DB, no LLM, no network) computed from data KritiFin already
stores, so they are fully unit-testable and cheap to run on every Client 360
load. Kept honest: scores derive only from available fields rather than
inventing data the schema does not hold.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

# Profile fields that make a client record "complete" for advice work.
_COMPLETENESS_FIELDS: tuple[tuple[str, str], ...] = (
    ("total_assets", "Total assets"),
    ("cash_savings", "Cash savings"),
    ("risk_score", "Risk score"),
    ("retirement_target_age", "Retirement target age"),
    ("last_review_date", "Last review date"),
)


def _is_present(value: Any) -> bool:
    return value is not None and value != ""


def _level_from_score(score: int) -> str:
    """Map a 0-100 risk-style score to a coarse band."""
    if score >= 67:
        return "HIGH"
    if score >= 34:
        return "MEDIUM"
    return "LOW"


def planning_completeness(client: dict[str, Any]) -> dict[str, Any]:
    """
    Percentage of key profile fields populated, plus the labels still missing.

    Returns ``{"score": int 0-100, "missing": list[str]}``.
    """
    present = [label for key, label in _COMPLETENESS_FIELDS if _is_present(client.get(key))]
    missing = [label for key, label in _COMPLETENESS_FIELDS if not _is_present(client.get(key))]
    total = len(_COMPLETENESS_FIELDS)
    score = round(100 * len(present) / total) if total else 0
    return {"score": score, "missing": missing}


def _months_since(last_review: Optional[date], today: date) -> Optional[int]:
    if last_review is None:
        return None
    return (today.year - last_review.year) * 12 + (today.month - last_review.month)


def at_risk_score(
    last_review: Optional[date],
    today: date,
    overdue_follow_ups: int,
    high_priority_alerts: int,
) -> dict[str, Any]:
    """
    Heuristic engagement-risk score (0-100) from review recency, overdue
    follow-ups, and open high-priority items.

    Returns ``{"score": int, "level": str, "rationale": str}``.
    """
    score = 0
    reasons: list[str] = []

    months = _months_since(last_review, today)
    if months is None:
        score += 50
        reasons.append("no review on file")
    elif months >= 18:
        score += 50
        reasons.append(f"last review {months} months ago")
    elif months >= 12:
        score += 35
        reasons.append(f"review overdue ({months} months)")
    elif months >= 9:
        score += 15
        reasons.append("review approaching")

    if overdue_follow_ups > 0:
        score += min(30, overdue_follow_ups * 15)
        reasons.append(f"{overdue_follow_ups} overdue follow-up(s)")

    if high_priority_alerts > 0:
        score += min(20, high_priority_alerts * 10)
        reasons.append(f"{high_priority_alerts} high-priority item(s)")

    score = max(0, min(100, score))
    rationale = "; ".join(reasons) if reasons else "engaged: recent review, no overdue items"
    return {"score": score, "level": _level_from_score(score), "rationale": rationale}


def next_best_actions(
    *,
    completeness: dict[str, Any],
    at_risk: dict[str, Any],
    review_overdue: bool,
    overdue_follow_up_titles: list[str],
    top_pending_title: Optional[str],
    limit: int = 4,
) -> list[dict[str, str]]:
    """
    Rank concrete next actions for a client from the computed signals.

    Returns an ordered list of ``{"action": str, "reason": str, "priority": str}``.
    """
    actions: list[dict[str, str]] = []

    if review_overdue:
        actions.append(
            {
                "action": "Book the annual review",
                "reason": "Review is overdue — Consumer Duty expects ongoing-service evidence.",
                "priority": "HIGH",
            }
        )

    for title in overdue_follow_up_titles:
        actions.append(
            {
                "action": f"Chase: {title}",
                "reason": "Follow-up is past its due date.",
                "priority": "HIGH",
            }
        )

    if completeness.get("missing"):
        missing = ", ".join(completeness["missing"])
        actions.append(
            {
                "action": "Complete the fact-find",
                "reason": f"Missing: {missing}.",
                "priority": "MEDIUM",
            }
        )

    if top_pending_title:
        actions.append(
            {
                "action": f"Action: {top_pending_title}",
                "reason": "Next upcoming priority for this client.",
                "priority": "MEDIUM",
            }
        )

    if at_risk.get("level") == "HIGH" and not review_overdue:
        actions.append(
            {
                "action": "Proactively reach out",
                "reason": f"At-risk signals: {at_risk.get('rationale', '')}.",
                "priority": "MEDIUM",
            }
        )

    return actions[:limit]
