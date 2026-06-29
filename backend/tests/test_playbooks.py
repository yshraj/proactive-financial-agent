"""Tests for the playbook catalog and alert-set builder."""
from __future__ import annotations

from datetime import date

import pytest

from app.services.playbooks import (
    PLAYBOOKS,
    build_playbook_alerts,
    list_playbooks,
)

TODAY = date(2026, 6, 29)

VALID_TYPES = {"DEADLINE", "OPPORTUNITY", "COMPLIANCE", "FOLLOW_UP"}
VALID_PRIORITIES = {"HIGH", "MEDIUM", "LOW"}


def test_list_playbooks_metadata():
    items = list_playbooks()
    assert len(items) == len(PLAYBOOKS)
    for item in items:
        assert item["id"] in PLAYBOOKS
        assert item["task_count"] >= 1
        assert item["name"]


def test_build_alerts_dates_relative_to_today():
    alerts = build_playbook_alerts("annual_review", TODAY)
    assert len(alerts) == len(PLAYBOOKS["annual_review"]["tasks"])
    # All trigger dates are in the future relative to the reference date.
    for a in alerts:
        assert a["trigger_date"] > TODAY.isoformat()
        assert a["type"] in VALID_TYPES
        assert a["priority"] in VALID_PRIORITIES
        assert a["title"]


def test_build_alerts_unknown_playbook_raises():
    with pytest.raises(KeyError):
        build_playbook_alerts("does_not_exist", TODAY)


def test_each_playbook_builds():
    for pid in PLAYBOOKS:
        alerts = build_playbook_alerts(pid, TODAY)
        assert alerts and all("trigger_date" in a for a in alerts)
