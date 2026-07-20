"""Front-door access-code gate: config helpers, the request dependency, and
the per-session rate-limit keying that the gate plumbs through.

The endpoint tests hit /api/access/check, which depends only on the gate (no
tenant, no DB), so they run without pgserver.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import security


# ---------------------------------------------------------------------------
# access_code_configured / access_code_matches (constant-time)
# ---------------------------------------------------------------------------


def test_access_code_unset_means_gate_disabled(monkeypatch):
    monkeypatch.delenv("ACCESS_CODE", raising=False)
    assert security.access_code_configured() is False
    # Nothing matches when unset — callers must check *_configured first.
    assert security.access_code_matches("anything") is False
    assert security.access_code_matches(None) is False


def test_access_code_matches_when_configured(monkeypatch):
    monkeypatch.setenv("ACCESS_CODE", "open-sesame")
    assert security.access_code_configured() is True
    assert security.access_code_matches("open-sesame") is True
    assert security.access_code_matches(" open-sesame ") is True  # trimmed
    assert security.access_code_matches("nope") is False
    assert security.access_code_matches(None) is False


# ---------------------------------------------------------------------------
# _rate_limit_key: per-user, per-session, per-IP layering
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(self, headers=None, tenant=None, client_host="1.2.3.4"):
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


def test_rate_limit_key_prefers_real_user(monkeypatch):
    from app.context import TenantContext

    ctx = TenantContext(org_id="org-1", user_id="user-9", role="adviser")
    req = _FakeRequest(headers={"X-Session-Id": "sess-abc"}, tenant=ctx)
    assert security._rate_limit_key(req) == "org:org-1:user-9"


def test_rate_limit_key_uses_session_for_shared_tenant():
    from app.context import TenantContext

    ctx = TenantContext(org_id="org-1", user_id=None, role="demo")
    req = _FakeRequest(headers={"X-Session-Id": "sess-abc"}, tenant=ctx)
    assert security._rate_limit_key(req) == "org:org-1:sess:sess-abc"


def test_rate_limit_key_falls_back_to_ip_without_session():
    from app.context import TenantContext

    ctx = TenantContext(org_id="org-1", user_id=None, role="demo")
    req = _FakeRequest(headers={}, tenant=ctx, client_host="9.9.9.9")
    assert security._rate_limit_key(req) == "org:org-1:ip:9.9.9.9"


# ---------------------------------------------------------------------------
# The gate as wired into the app (endpoint-level, no DB)
# ---------------------------------------------------------------------------


@pytest.fixture()
def gate_client(monkeypatch):
    # required-mode auth is already satisfied by conftest's SUPABASE_JWT_SECRET.
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_check_passes_when_gate_disabled(gate_client, monkeypatch):
    monkeypatch.delenv("ACCESS_CODE", raising=False)
    res = gate_client.get("/api/access/check")
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_check_rejects_without_code(gate_client, monkeypatch):
    monkeypatch.setenv("ACCESS_CODE", "letmein")
    res = gate_client.get("/api/access/check")
    assert res.status_code == 401


def test_check_rejects_wrong_code(gate_client, monkeypatch):
    monkeypatch.setenv("ACCESS_CODE", "letmein")
    res = gate_client.get("/api/access/check", headers={"X-Access-Code": "wrong"})
    assert res.status_code == 401


def test_check_accepts_correct_code(gate_client, monkeypatch):
    monkeypatch.setenv("ACCESS_CODE", "letmein")
    res = gate_client.get("/api/access/check", headers={"X-Access-Code": "letmein"})
    assert res.status_code == 200


def test_gate_blocks_api_route_before_auth(gate_client, monkeypatch):
    # With the gate on, an /api route is rejected for a missing code even before
    # tenant auth would run.
    monkeypatch.setenv("ACCESS_CODE", "letmein")
    res = gate_client.get("/api/monitor/clients")
    assert res.status_code == 401


def test_health_is_never_gated(gate_client, monkeypatch):
    monkeypatch.setenv("ACCESS_CODE", "letmein")
    res = gate_client.get("/health")
    assert res.status_code == 200
