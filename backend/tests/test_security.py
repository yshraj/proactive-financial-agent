"""Unit tests for the M0 security layer (auth gate + data-reset flag)."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app import security


def test_data_reset_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_DATA_RESET", raising=False)
    assert security.data_reset_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes"])
def test_data_reset_enabled_truthy(monkeypatch, val):
    monkeypatch.setenv("ALLOW_DATA_RESET", val)
    assert security.data_reset_enabled() is True


def test_data_reset_enabled_falsey(monkeypatch):
    monkeypatch.setenv("ALLOW_DATA_RESET", "no")
    assert security.data_reset_enabled() is False


def test_require_api_key_open_when_unset(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    # Should not raise when no key is configured (local/dev).
    asyncio.run(security.require_api_key(x_api_key=None))


def test_require_api_key_rejects_missing(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-123")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(security.require_api_key(x_api_key=None))
    assert exc.value.status_code == 401


def test_require_api_key_rejects_wrong(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-123")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(security.require_api_key(x_api_key="nope"))
    assert exc.value.status_code == 401


def test_require_api_key_accepts_correct(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-123")
    asyncio.run(security.require_api_key(x_api_key="secret-123"))
