"""
Playbooks: reusable task templates that expand into a set of alerts for a client.

Pure (no DB): the catalog and the alert-set builder are fully unit-testable. The
monitor router applies a playbook by inserting the generated alerts. Trigger
dates are computed relative to a reference date so applying a playbook always
lands tasks in a sensible window.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

# Each task: days offset from "today", alert type, priority, title, description.
PLAYBOOKS: dict[str, dict[str, Any]] = {
    "annual_review": {
        "name": "Annual review preparation",
        "description": "Standard steps to prepare and run an annual client review.",
        "tasks": [
            {"offset_days": 7, "type": "FOLLOW_UP", "priority": "MEDIUM",
             "title": "Request up-to-date documents", "description": "Ask the client for latest statements and any changes."},
            {"offset_days": 14, "type": "DEADLINE", "priority": "HIGH",
             "title": "Prepare review pack", "description": "Refresh cashflow, valuations and performance vs objectives."},
            {"offset_days": 21, "type": "DEADLINE", "priority": "HIGH",
             "title": "Hold annual review meeting", "description": "Conduct the review and capture a Consumer Duty note."},
        ],
    },
    "new_client_onboarding": {
        "name": "New client onboarding",
        "description": "Onboard a new client from fact-find to first plan.",
        "tasks": [
            {"offset_days": 2, "type": "FOLLOW_UP", "priority": "HIGH",
             "title": "Send welcome pack and LOA", "description": "Issue letters of authority and onboarding forms."},
            {"offset_days": 10, "type": "COMPLIANCE", "priority": "HIGH",
             "title": "Complete fact-find and ATR", "description": "Capture circumstances, attitude to risk and capacity for loss."},
            {"offset_days": 21, "type": "OPPORTUNITY", "priority": "MEDIUM",
             "title": "Present initial recommendations", "description": "Share the first suitability report and plan."},
        ],
    },
    "protection_review": {
        "name": "Protection review",
        "description": "Review protection cover against current needs.",
        "tasks": [
            {"offset_days": 5, "type": "FOLLOW_UP", "priority": "MEDIUM",
             "title": "Gather existing policy details", "description": "Collect current life, CIC and income protection cover."},
            {"offset_days": 12, "type": "OPPORTUNITY", "priority": "HIGH",
             "title": "Assess protection gap", "description": "Compare cover to income, debts and dependants."},
        ],
    },
}


def list_playbooks() -> list[dict[str, Any]]:
    """Return catalog metadata (id, name, description, task_count)."""
    return [
        {
            "id": pid,
            "name": pb["name"],
            "description": pb["description"],
            "task_count": len(pb["tasks"]),
        }
        for pid, pb in PLAYBOOKS.items()
    ]


def build_playbook_alerts(playbook_id: str, today: date) -> list[dict[str, Any]]:
    """
    Expand a playbook into alert dicts (trigger_date as ISO string) ready to insert.

    Raises:
        KeyError: if the playbook id is unknown.
    """
    playbook = PLAYBOOKS[playbook_id]
    alerts = []
    for task in playbook["tasks"]:
        alerts.append(
            {
                "trigger_date": (today + timedelta(days=task["offset_days"])).isoformat(),
                "type": task["type"],
                "priority": task["priority"],
                "title": task["title"],
                "description": task["description"],
            }
        )
    return alerts
