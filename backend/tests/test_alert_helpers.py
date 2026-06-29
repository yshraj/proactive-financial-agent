"""Tests for alert sorting/helpers (regression: pulse crash on populated data)."""
from __future__ import annotations

from types import SimpleNamespace

from app.services.alert_helpers import alert_sort_key, synthetic_review_overdue


def test_sort_key_on_object_without_get():
    # Regression: AlertOut-like objects have no .get; must not raise.
    alert = SimpleNamespace(priority="HIGH", trigger_date="2026-07-01")
    assert alert_sort_key(alert) == ("2026-07-01", 0)


def test_sort_key_on_dict():
    alert = {"priority": "MEDIUM", "trigger_date": "2026-07-02"}
    assert alert_sort_key(alert) == ("2026-07-02", 1)


def test_sort_key_unknown_priority_defaults_last():
    assert alert_sort_key(SimpleNamespace(priority=None, trigger_date="x"))[1] == 2


def test_sort_orders_high_first_within_same_date():
    alerts = [
        SimpleNamespace(priority="LOW", trigger_date="2026-07-01"),
        SimpleNamespace(priority="HIGH", trigger_date="2026-07-01"),
        SimpleNamespace(priority="MEDIUM", trigger_date="2026-07-01"),
    ]
    alerts.sort(key=alert_sort_key)
    assert [a.priority for a in alerts] == ["HIGH", "MEDIUM", "LOW"]


def test_sort_mixed_objects_and_dicts_does_not_raise():
    mixed = [
        SimpleNamespace(priority="HIGH", trigger_date="2026-07-03"),
        synthetic_review_overdue("c1", "Test Client", "2026-06-29"),  # returns a dict
    ]
    mixed.sort(key=alert_sort_key)
    assert len(mixed) == 2
