"""Unit tests for the fail-closed auth mode, API key check, and data-reset flag."""
from __future__ import annotations

import pytest

from app import security


# ---------------------------------------------------------------------------
# AUTH_MODE / enforce_auth_mode (fail closed)
# ---------------------------------------------------------------------------


def _clear_auth_env(monkeypatch):
    for var in ("AUTH_MODE", "SUPABASE_URL", "SUPABASE_JWT_SECRET", "API_KEY", "ENV"):
        monkeypatch.delenv(var, raising=False)


def test_default_mode_is_required(monkeypatch):
    _clear_auth_env(monkeypatch)
    assert security.auth_mode() == security.AUTH_MODE_REQUIRED


def test_unknown_mode_fails_closed_to_required(monkeypatch):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("AUTH_MODE", "open-sesame")
    assert security.auth_mode() == security.AUTH_MODE_REQUIRED


def test_required_mode_without_supabase_refuses_to_boot(monkeypatch):
    _clear_auth_env(monkeypatch)
    with pytest.raises(RuntimeError, match="AUTH_MODE=required"):
        security.enforce_auth_mode()


def test_required_mode_without_supabase_refuses_even_in_dev(monkeypatch):
    # Fail closed in EVERY environment, not just production.
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("ENV", "development")
    with pytest.raises(RuntimeError):
        security.enforce_auth_mode()


def test_required_mode_boots_with_supabase_url(monkeypatch):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    security.enforce_auth_mode()  # should not raise


def test_required_mode_boots_with_jwt_secret(monkeypatch):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "s3cret")
    security.enforce_auth_mode()


def test_api_key_alone_does_not_satisfy_required_mode(monkeypatch):
    # A service credential is not user auth; boot must still refuse.
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("API_KEY", "svc-key")
    with pytest.raises(RuntimeError):
        security.enforce_auth_mode()


def test_demo_mode_boots_outside_production(monkeypatch):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("AUTH_MODE", "demo")
    security.enforce_auth_mode()


@pytest.mark.parametrize("env_value", ["production", "prod", "PRODUCTION"])
def test_demo_mode_refused_in_production(monkeypatch, env_value):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("AUTH_MODE", "demo")
    monkeypatch.setenv("ENV", env_value)
    with pytest.raises(RuntimeError, match="demo"):
        security.enforce_auth_mode()


# ---------------------------------------------------------------------------
# Service API key
# ---------------------------------------------------------------------------


def test_api_key_matches_constant_time(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-123")
    assert security.api_key_matches("secret-123") is True
    assert security.api_key_matches("nope") is False
    assert security.api_key_matches(None) is False


def test_api_key_never_matches_when_unset(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    assert security.api_key_matches("anything") is False
    assert security.api_key_configured() is False


# ---------------------------------------------------------------------------
# Data reset flag
# ---------------------------------------------------------------------------


def test_data_reset_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_DATA_RESET", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    assert security.data_reset_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes"])
def test_data_reset_enabled_truthy(monkeypatch, val):
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setenv("ALLOW_DATA_RESET", val)
    assert security.data_reset_enabled() is True


def test_data_reset_enabled_falsey(monkeypatch):
    monkeypatch.setenv("ALLOW_DATA_RESET", "no")
    assert security.data_reset_enabled() is False


def test_data_reset_true_is_ignored_in_production(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("ALLOW_DATA_RESET", "true")
    assert security.data_reset_enabled() is False


def test_data_reset_force_works_in_production(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("ALLOW_DATA_RESET", "force")
    assert security.data_reset_enabled() is True
