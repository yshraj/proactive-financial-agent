"""Phase 2 — daily cost budgets, the structured 429, and hit logging.

The daily budgets are shared slowapi limits; exceeding one must return a clean,
machine-readable 429 (never a 500) and emit a queryable log line. Limits are
disabled globally in tests (conftest), so these tests opt the limiter back on
around a unique-keyed request set to stay isolated.
"""
from __future__ import annotations

import logging

import pytest

from app import security
from tests.conftest import auth_headers_for


# ---------------------------------------------------------------------------
# limit_type_for classification (pure)
# ---------------------------------------------------------------------------


def test_limit_type_prefers_shared_scope():
    assert security.limit_type_for("llm", "/api/anything") == "llm"
    assert security.limit_type_for("ingestion", "/api/anything") == "ingestion"


def test_limit_type_infers_from_path():
    assert security.limit_type_for(None, "/api/ingest/upload") == "ingestion"
    assert security.limit_type_for(None, "/api/chat/") == "llm"
    assert security.limit_type_for(None, "/api/monitor/digest") == "llm"
    assert security.limit_type_for("some-endpoint", "/api/monitor/clients") == "request"


# ---------------------------------------------------------------------------
# Daily ingestion budget end-to-end
# ---------------------------------------------------------------------------


@pytest.fixture()
def limiter_on():
    """Enable the limiter and start from a clean in-memory counter."""
    prev = security.limiter.enabled
    security.limiter.enabled = True
    security.limiter._storage.reset()
    yield
    security.limiter._storage.reset()
    security.limiter.enabled = prev


def test_ingestion_daily_budget_returns_structured_429(
    api_client, clean_db, org_a, limiter_on, caplog
):
    headers = auth_headers_for(org_a)
    # INGEST_DAILY_LIMIT defaults to 5/day; the short text 400s but still counts.
    body = {"text": "hi"}
    for _ in range(5):
        r = api_client.post("/api/ingest/transcript", json=body, headers=headers)
        assert r.status_code != 429  # within budget

    with caplog.at_level(logging.WARNING, logger="jarvis.ratelimit"):
        blocked = api_client.post("/api/ingest/transcript", json=body, headers=headers)

    assert blocked.status_code == 429
    payload = blocked.json()
    assert payload["error"] == "rate_limit"
    assert payload["limit_type"] == "ingestion"
    assert "reset_at" in payload
    assert "Retry-After" in blocked.headers
    # The hit is logged (queryable) with its structured fields.
    assert any(
        getattr(rec, "event", None) == "rate_limit_hit"
        and getattr(rec, "limit_type", None) == "ingestion"
        for rec in caplog.records
    )


def test_budget_isolated_per_key(api_client, clean_db, org_a, org_b, limiter_on):
    """One session exhausting its budget does not block another."""
    body = {"text": "hi"}
    for _ in range(6):
        api_client.post("/api/ingest/transcript", json=body, headers=auth_headers_for(org_a))
    # org_a is now over budget; org_b starts fresh.
    r = api_client.post("/api/ingest/transcript", json=body, headers=auth_headers_for(org_b))
    assert r.status_code != 429
