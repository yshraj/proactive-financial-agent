"""Tests for data-handling & AI posture reporting."""
from __future__ import annotations

from app.services.posture import get_posture


def test_defaults_are_conservative():
    p = get_posture({})
    assert p["trains_on_client_data"] is False
    assert p["data_residency"] == "not configured"
    assert p["data_retention_days"] is None
    assert p["llm_provider"] == "openai"
    assert p["encryption_at_rest"] is False
    assert p["encryption_in_transit"] is True
    assert p["auth_required"] is False


def test_reads_configured_values():
    p = get_posture(
        {
            "DATA_RESIDENCY": "UK",
            "DATA_RETENTION_DAYS": "365",
            "LLM_PROVIDER": "Gemini",
            "ENCRYPTION_AT_REST": "true",
            "API_KEY": "secret",
        }
    )
    assert p["data_residency"] == "UK"
    assert p["data_retention_days"] == 365
    assert p["llm_provider"] == "gemini"
    assert p["encryption_at_rest"] is True
    assert p["auth_required"] is True


def test_invalid_retention_falls_back_to_none():
    assert get_posture({"DATA_RETENTION_DAYS": "abc"})["data_retention_days"] is None


def test_never_claims_training_on_client_data():
    # Even if someone sets a misleading env var, the app does not train.
    assert get_posture({"MODEL_TRAINING": "true"})["trains_on_client_data"] is False
