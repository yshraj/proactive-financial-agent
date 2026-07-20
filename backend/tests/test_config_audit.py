"""Phase 3 — the startup config audit names exactly what a deploy is missing."""
from __future__ import annotations

import pytest

from app.observability import startup_config_warnings


def _clear(monkeypatch, *names):
    for n in names:
        monkeypatch.delenv(n, raising=False)


def test_names_missing_core_vars(monkeypatch):
    _clear(
        monkeypatch,
        "DATABASE_URL", "QDRANT_URL", "OPENAI_API_KEY", "CORS_ORIGINS", "SENTRY_DSN",
        "GEMINI_API_KEY", "GOOGLE_API_KEY",
    )
    monkeypatch.setenv("AUTH_MODE", "demo")
    monkeypatch.delenv("ACCESS_CODE", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "openai")

    findings = startup_config_warnings()
    blob = "\n".join(findings)
    for expected in ["DATABASE_URL", "QDRANT_URL", "OPENAI_API_KEY", "ACCESS_CODE", "CORS_ORIGINS", "SENTRY_DSN"]:
        assert expected in blob, f"expected {expected} named in warnings"


def test_clean_config_has_no_warnings(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("AUTH_MODE", "demo")
    monkeypatch.setenv("ACCESS_CODE", "s3cret")
    monkeypatch.setenv("CORS_ORIGINS", "https://demo.example.com")
    monkeypatch.setenv("SENTRY_DSN", "https://x@sentry.io/1")
    assert startup_config_warnings() == []


def test_gemini_provider_checks_its_own_keys(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")
    monkeypatch.setenv("CORS_ORIGINS", "https://demo.example.com")
    monkeypatch.setenv("SENTRY_DSN", "https://x@sentry.io/1")
    monkeypatch.setenv("AUTH_MODE", "demo")
    monkeypatch.setenv("ACCESS_CODE", "s3cret")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    _clear(monkeypatch, "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY")
    findings = startup_config_warnings()
    assert any("gemini" in f.lower() for f in findings)
