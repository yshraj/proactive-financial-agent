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


class _FakeRequest:
    def __init__(self, headers=None, tenant=None, client_host="5.5.5.5"):
        self.headers = headers or {}

        class _State:
            pass

        self.state = _State()
        if tenant is not None:
            self.state.tenant = tenant

        class _Client:
            host = client_host

        self.client = _Client()
        self.scope = {"client": (client_host, 0)}


# ---------------------------------------------------------------------------
# Proxy-aware client IP + daily-budget key (the spoof-gap fix)
# ---------------------------------------------------------------------------


def test_client_ip_prefers_forwarded_for():
    req = _FakeRequest(headers={"X-Forwarded-For": "203.0.113.9, 10.0.0.1"}, client_host="10.0.0.1")
    assert security.client_ip_from(req) == "203.0.113.9"


def test_client_ip_uses_real_ip_header():
    req = _FakeRequest(headers={"X-Real-IP": "198.51.100.7"}, client_host="10.0.0.1")
    assert security.client_ip_from(req) == "198.51.100.7"


def test_client_ip_falls_back_to_peer():
    req = _FakeRequest(headers={}, client_host="192.0.2.44")
    assert security.client_ip_from(req) == "192.0.2.44"


def test_daily_budget_key_ignores_session_rotation():
    """The whole point: rotating X-Session-Id from the same IP must NOT mint a
    fresh daily budget."""
    from app.context import TenantContext

    demo = TenantContext(org_id="00000000-0000-0000-0000-000000000001", user_id=None, role="demo")
    key_a = security.daily_budget_key(
        _FakeRequest(headers={"X-Session-Id": "aaaa"}, tenant=demo, client_host="7.7.7.7")
    )
    key_b = security.daily_budget_key(
        _FakeRequest(headers={"X-Session-Id": "bbbb"}, tenant=demo, client_host="7.7.7.7")
    )
    assert key_a == key_b  # same IP -> same daily bucket regardless of session
    assert "7.7.7.7" in key_a


def test_daily_budget_key_authenticated_uses_user():
    from app.context import TenantContext

    ctx = TenantContext(org_id="org-9", user_id="user-3", role="adviser")
    key = security.daily_budget_key(
        _FakeRequest(headers={"X-Session-Id": "whatever"}, tenant=ctx)
    )
    assert key == "org:org-9:user-3"


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
