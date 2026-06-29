"""
Demo dataset for onboarding / first-run.

`build_sample_dataset` is pure (no DB): given a reference date it returns
realistic UK IFA clients, each with embedded alerts whose trigger dates are
positioned relative to "today" so the dashboard, overdue follow-ups, and
review-overdue logic all have something to show. The settings router inserts it.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

VALID_ALERT_TYPES = {"DEADLINE", "OPPORTUNITY", "COMPLIANCE", "FOLLOW_UP"}
VALID_PRIORITIES = {"HIGH", "MEDIUM", "LOW"}


def build_sample_dataset(today: date) -> list[dict[str, Any]]:
    """
    Return a list of sample client dicts, each with an ``alerts`` list.

    Dates are ISO strings. Includes at least one client overdue for review
    (last_review_date > 365 days ago) and at least one overdue follow-up so the
    proactive surfaces are populated on first load.
    """

    def iso(offset_days: int) -> str:
        return (today + timedelta(days=offset_days)).isoformat()

    return [
        {
            "full_name": "Alan & Lynne Partridge",
            "retirement_target_age": 65,
            "risk_score": 5,
            "total_assets": 895000,
            "cash_savings": 62000,
            "last_review_date": iso(-400),  # overdue for review
            "alerts": [
                {
                    "trigger_date": iso(3),
                    "type": "DEADLINE",
                    "priority": "HIGH",
                    "title": "Annual review due",
                    "description": "Scheduled annual review. Prepare a cashflow update.",
                },
                {
                    "trigger_date": iso(-8),
                    "type": "FOLLOW_UP",
                    "priority": "MEDIUM",
                    "title": "Waiting on client: pension decision",
                    "description": "Alan to confirm the pension contribution increase.",
                },
            ],
        },
        {
            "full_name": "David & Sarah Chen",
            "retirement_target_age": 60,
            "risk_score": 6,
            "total_assets": 620000,
            "cash_savings": 58000,
            "last_review_date": iso(-120),
            "alerts": [
                {
                    "trigger_date": iso(6),
                    "type": "OPPORTUNITY",
                    "priority": "MEDIUM",
                    "title": "ISA allowance unused",
                    "description": "£20,000 ISA allowance still available this tax year.",
                },
            ],
        },
        {
            "full_name": "Priya & Anil Sharma",
            "retirement_target_age": 62,
            "risk_score": 4,
            "total_assets": 430000,
            "cash_savings": 41000,
            "last_review_date": iso(-200),
            "alerts": [
                {
                    "trigger_date": iso(9),
                    "type": "COMPLIANCE",
                    "priority": "HIGH",
                    "title": "Estate planning gap",
                    "description": "LPAs not in place; wills update flagged.",
                },
                {
                    "trigger_date": iso(-21),
                    "type": "FOLLOW_UP",
                    "priority": "HIGH",
                    "title": "Waiting on client: signed LOA",
                    "description": "Awaiting signed letter of authority.",
                },
            ],
        },
        {
            "full_name": "The Williams Family",
            "retirement_target_age": 67,
            "risk_score": 3,
            "total_assets": 310000,
            "cash_savings": 28000,
            "last_review_date": iso(-500),  # overdue for review
            "alerts": [
                {
                    "trigger_date": iso(15),
                    "type": "OPPORTUNITY",
                    "priority": "LOW",
                    "title": "Pension contribution headroom",
                    "description": "Annual allowance partly unused.",
                },
            ],
        },
    ]
