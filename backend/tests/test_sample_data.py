"""Tests for the onboarding sample dataset builder."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.services.sample_data import (
    VALID_ALERT_TYPES,
    VALID_PRIORITIES,
    build_sample_dataset,
)

TODAY = date(2026, 6, 29)


def test_returns_clients_with_alerts():
    data = build_sample_dataset(TODAY)
    assert len(data) >= 3
    for client in data:
        assert client["full_name"].strip()
        assert isinstance(client["alerts"], list) and client["alerts"]


def test_risk_scores_in_range():
    for client in build_sample_dataset(TODAY):
        assert 1 <= client["risk_score"] <= 10


def test_alert_types_and_priorities_valid():
    for client in build_sample_dataset(TODAY):
        for alert in client["alerts"]:
            assert alert["type"] in VALID_ALERT_TYPES
            assert alert["priority"] in VALID_PRIORITIES
            # trigger_date parses as an ISO date
            datetime.strptime(alert["trigger_date"], "%Y-%m-%d")


def test_includes_a_review_overdue_client():
    cutoff = TODAY - timedelta(days=365)
    overdue = [
        c
        for c in build_sample_dataset(TODAY)
        if date.fromisoformat(c["last_review_date"]) < cutoff
    ]
    assert overdue, "expected at least one client overdue for review"


def test_includes_an_overdue_follow_up():
    has_overdue_follow_up = any(
        a["type"] == "FOLLOW_UP" and date.fromisoformat(a["trigger_date"]) < TODAY
        for c in build_sample_dataset(TODAY)
        for a in c["alerts"]
    )
    assert has_overdue_follow_up


def test_dates_relative_to_reference():
    # A different reference date shifts the trigger dates accordingly.
    other = date(2030, 1, 1)
    first_alert = build_sample_dataset(other)[0]["alerts"][0]
    assert date.fromisoformat(first_alert["trigger_date"]).year == 2030
