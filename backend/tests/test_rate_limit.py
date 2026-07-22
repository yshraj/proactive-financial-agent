"""Per-minute abuse protection, structured 429s, and hit logging.

Lifetime credits are finite and never reset. Slowapi only guards short request
bursts; exceeding that guard must return a clean, machine-readable 429.
Limits are disabled globally in tests (conftest), so these tests opt in.
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
# Proxy-aware client IP
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


def test_all_slowapi_hits_are_classified_as_temporary_request_limits():
    assert security.limit_type_for("legacy-scope", "/api/chat/") == "request"
    assert security.limit_type_for(None, "/api/ingest/upload") == "request"


# ---------------------------------------------------------------------------
# Per-minute abuse protection (lifetime credits have no reset budget)
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


def test_credit_endpoint_has_no_daily_budget(api_client, clean_db, org_a, limiter_on):
    headers = auth_headers_for(org_a)
    body = {"text": "hi"}
    for _ in range(6):
        r = api_client.post("/api/ingest/transcript", json=body, headers=headers)
        assert r.status_code == 400


def test_ingestion_per_minute_limit_remains_structured(
    api_client, clean_db, org_a, limiter_on, caplog
):
    headers = auth_headers_for(org_a)
    body = {"text": "hi"}
    for _ in range(30):
        assert api_client.post(
            "/api/ingest/transcript", json=body, headers=headers
        ).status_code == 400
    with caplog.at_level(logging.WARNING, logger="jarvis.ratelimit"):
        blocked = api_client.post(
            "/api/ingest/transcript", json=body, headers=headers
        )
    assert blocked.status_code == 429
    assert blocked.json()["error"] == {
        "code": "rate_limited",
        "message": "Too many requests. Please wait a moment and try again.",
        "retryable": True,
    }
    assert blocked.json()["limit_type"] == "request"
