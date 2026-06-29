"""Tests for book-level analytics aggregation."""
from __future__ import annotations

from datetime import date

from app.services.analytics import compute_book_analytics

TODAY = date(2026, 6, 29)


def test_empty_book():
    result = compute_book_analytics([], TODAY)
    assert result == {
        "clients_total": 0,
        "total_aum": 0,
        "average_risk_score": None,
        "reviews_overdue": 0,
    }


def test_aggregates_aum_and_average_risk():
    clients = [
        {"total_assets": 100000, "risk_score": 4, "last_review_date": date(2026, 6, 1)},
        {"total_assets": 300000, "risk_score": 6, "last_review_date": date(2026, 1, 1)},
    ]
    result = compute_book_analytics(clients, TODAY)
    assert result["clients_total"] == 2
    assert result["total_aum"] == 400000
    assert result["average_risk_score"] == 5.0
    assert result["reviews_overdue"] == 0


def test_counts_reviews_overdue_and_null():
    clients = [
        {"total_assets": None, "risk_score": None, "last_review_date": None},  # overdue (no review)
        {"total_assets": 50000, "risk_score": 3, "last_review_date": date(2024, 1, 1)},  # overdue
        {"total_assets": 50000, "risk_score": 3, "last_review_date": date(2026, 6, 1)},  # recent
    ]
    result = compute_book_analytics(clients, TODAY)
    assert result["reviews_overdue"] == 2
    assert result["total_aum"] == 100000
    assert result["average_risk_score"] == 3.0


def test_missing_keys_are_tolerated():
    result = compute_book_analytics([{}, {}], TODAY)
    assert result["clients_total"] == 2
    assert result["total_aum"] == 0
    assert result["average_risk_score"] is None
    assert result["reviews_overdue"] == 2  # both have no review date
