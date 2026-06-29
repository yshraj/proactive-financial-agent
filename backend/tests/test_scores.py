"""Tests for deterministic client-intelligence scores and next-best-action."""
from __future__ import annotations

from datetime import date

from app.services.scores import (
    at_risk_score,
    next_best_actions,
    planning_completeness,
)

TODAY = date(2026, 6, 29)


def test_completeness_full():
    client = {
        "total_assets": 100,
        "cash_savings": 10,
        "risk_score": 5,
        "retirement_target_age": 65,
        "last_review_date": TODAY,
    }
    result = planning_completeness(client)
    assert result["score"] == 100
    assert result["missing"] == []


def test_completeness_partial_reports_missing():
    result = planning_completeness({"total_assets": 100, "risk_score": 5})
    assert result["score"] == 40  # 2 of 5 present -> 40%
    assert "Cash savings" in result["missing"]
    assert "Last review date" in result["missing"]


def test_completeness_empty_string_counts_as_missing():
    result = planning_completeness({"total_assets": "", "cash_savings": None})
    assert result["score"] == 0


def test_at_risk_no_review_is_elevated():
    result = at_risk_score(None, TODAY, overdue_follow_ups=0, high_priority_alerts=0)
    assert result["score"] >= 50
    assert result["level"] in ("MEDIUM", "HIGH")
    assert "no review" in result["rationale"]


def test_at_risk_recent_review_low():
    result = at_risk_score(
        date(2026, 5, 1), TODAY, overdue_follow_ups=0, high_priority_alerts=0
    )
    assert result["score"] == 0
    assert result["level"] == "LOW"


def test_at_risk_accumulates_and_caps_at_100():
    result = at_risk_score(
        None, TODAY, overdue_follow_ups=10, high_priority_alerts=10
    )
    assert result["score"] == 100
    assert result["level"] == "HIGH"


def test_at_risk_overdue_review_band():
    # 13 months ago -> overdue band (>=12, <18)
    result = at_risk_score(
        date(2025, 5, 1), TODAY, overdue_follow_ups=0, high_priority_alerts=0
    )
    assert result["score"] == 35


def test_nba_prioritises_overdue_review_first():
    actions = next_best_actions(
        completeness={"score": 100, "missing": []},
        at_risk={"score": 50, "level": "MEDIUM", "rationale": "x"},
        review_overdue=True,
        overdue_follow_up_titles=["Signed LOA"],
        top_pending_title="ISA top-up",
    )
    assert actions[0]["action"] == "Book the annual review"
    assert actions[0]["priority"] == "HIGH"
    assert any("Signed LOA" in a["action"] for a in actions)


def test_nba_suggests_factfind_when_incomplete():
    actions = next_best_actions(
        completeness={"score": 40, "missing": ["Risk score", "Cash savings"]},
        at_risk={"score": 10, "level": "LOW", "rationale": "ok"},
        review_overdue=False,
        overdue_follow_up_titles=[],
        top_pending_title=None,
    )
    assert any(a["action"] == "Complete the fact-find" for a in actions)


def test_nba_respects_limit():
    actions = next_best_actions(
        completeness={"score": 0, "missing": ["a"]},
        at_risk={"score": 90, "level": "HIGH", "rationale": "x"},
        review_overdue=True,
        overdue_follow_up_titles=["f1", "f2", "f3", "f4", "f5"],
        top_pending_title="p",
        limit=4,
    )
    assert len(actions) == 4
