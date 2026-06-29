"""Tests for deterministic compliance signal detection."""
from __future__ import annotations

from app.services.compliance import scan_text


def test_empty_text_no_signals():
    result = scan_text("")
    assert result["vulnerability_signals"] == []
    assert result["consumer_duty_flags"] == []
    assert result["summary"] == {"vulnerability_count": 0, "consumer_duty_count": 0}


def test_detects_health_vulnerability():
    result = scan_text("Client mentioned a recent cancer diagnosis during the meeting.")
    cats = {s["category"] for s in result["vulnerability_signals"]}
    assert "Health" in cats
    assert result["summary"]["vulnerability_count"] >= 1


def test_detects_life_event_and_resilience():
    result = scan_text("Following his redundancy the client is now in arrears on the mortgage.")
    cats = {s["category"] for s in result["vulnerability_signals"]}
    assert "Life events" in cats
    assert "Resilience" in cats


def test_detects_consumer_duty_understanding():
    result = scan_text("The client said the charges were unclear and they did not understand the fees.")
    outcomes = {s["outcome"] for s in result["consumer_duty_flags"]}
    assert "Consumer understanding" in outcomes


def test_word_boundary_prevents_false_positive():
    # "skill" contains "ill" but must not trigger the Health driver.
    result = scan_text("The adviser showed great skill and billing was handled well.")
    cats = {s["category"] for s in result["vulnerability_signals"]}
    assert "Health" not in cats


def test_excerpt_includes_context():
    result = scan_text("Earlier in the call the client disclosed a disability that affects mobility.")
    signal = result["vulnerability_signals"][0]
    assert "disability" in signal["excerpt"].lower()


def test_case_insensitive():
    result = scan_text("DIVORCE proceedings are ongoing.")
    cats = {s["category"] for s in result["vulnerability_signals"]}
    assert "Life events" in cats
