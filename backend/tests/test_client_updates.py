"""Tests for manual client-edit validation/coercion."""
from __future__ import annotations

import pytest

from app.services.client_updates import validate_client_update


def test_empty_update_rejected():
    with pytest.raises(ValueError):
        validate_client_update({})


def test_ignores_unknown_fields_but_keeps_editable():
    out = validate_client_update({"full_name": "Jane Doe", "secret": "x"})
    assert out == {"full_name": "Jane Doe"}


def test_full_name_trimmed_and_required():
    assert validate_client_update({"full_name": "  Bob  "}) == {"full_name": "Bob"}
    with pytest.raises(ValueError):
        validate_client_update({"full_name": "   "})


def test_risk_score_range_enforced():
    assert validate_client_update({"risk_score": 7}) == {"risk_score": 7}
    assert validate_client_update({"risk_score": "5"}) == {"risk_score": 5}
    for bad in (0, 11, -3):
        with pytest.raises(ValueError):
            validate_client_update({"risk_score": bad})


def test_risk_score_can_be_cleared():
    assert validate_client_update({"risk_score": None}) == {"risk_score": None}


def test_retirement_age_range():
    assert validate_client_update({"retirement_target_age": 65}) == {"retirement_target_age": 65}
    with pytest.raises(ValueError):
        validate_client_update({"retirement_target_age": 20})


def test_money_non_negative():
    assert validate_client_update({"total_assets": "1000.5"}) == {"total_assets": 1000.5}
    with pytest.raises(ValueError):
        validate_client_update({"cash_savings": -1})


def test_last_review_date_format():
    assert validate_client_update({"last_review_date": "2026-01-15"}) == {
        "last_review_date": "2026-01-15"
    }
    assert validate_client_update({"last_review_date": ""}) == {"last_review_date": None}
    with pytest.raises(ValueError):
        validate_client_update({"last_review_date": "15/01/2026"})


def test_bool_rejected_as_number():
    with pytest.raises(ValueError):
        validate_client_update({"risk_score": True})


def test_multiple_fields_combined():
    out = validate_client_update(
        {"full_name": "Acme Ltd", "total_assets": 50000, "risk_score": 4}
    )
    assert out == {"full_name": "Acme Ltd", "total_assets": 50000.0, "risk_score": 4}
