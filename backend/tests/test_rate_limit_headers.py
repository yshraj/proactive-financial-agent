"""
Regression: rate-limited endpoints must work with the limiter ENABLED.

The suite normally runs with RATE_LIMIT_ENABLED=false, which skips slowapi's
wrapper entirely — that's how a production-only crash slipped through:
with ``headers_enabled=True``, slowapi injects X-RateLimit-* headers after the
endpoint returns, and raises

    Exception: parameter `response` must be an instance of
    starlette.responses.Response

for any decorated endpoint that returns a Pydantic model without declaring a
``response: Response`` parameter for FastAPI to inject. Every decorated
endpoint carries that parameter now; these tests flip the limiter on and hit
representative endpoints of each shape to keep it that way.
"""
from __future__ import annotations

import pytest

from app import security
from tests.conftest import auth_headers_for, seed_client


@pytest.fixture()
def rate_limiting_enabled(monkeypatch):
    monkeypatch.setattr(security.limiter, "enabled", True)
    yield
    # monkeypatch restores the attribute automatically.


def _assert_rate_limit_headers(resp):
    assert "x-ratelimit-limit" in resp.headers, dict(resp.headers)
    assert "x-ratelimit-remaining" in resp.headers


def test_async_multipart_endpoint_with_limiter_enabled(
    api_client, clean_db, org_a, rate_limiting_enabled
):
    """The exact production crash site: async upload returning a Pydantic model."""
    resp = api_client.post(
        "/api/ingest/upload-async",
        files={"file": ("note.md", b"# Meeting\nPension discussed at length today.", "text/markdown")},
        headers=auth_headers_for(org_a),
    )
    assert resp.status_code == 202, resp.text
    _assert_rate_limit_headers(resp)


def test_sync_json_endpoint_with_limiter_enabled(
    api_client, clean_db, org_a, rate_limiting_enabled
):
    resp = api_client.post(
        "/api/compliance/scan",
        json={"text": "Client mentioned a recent cancer diagnosis and felt unclear about fees."},
        headers=auth_headers_for(org_a),
    )
    assert resp.status_code == 200, resp.text
    _assert_rate_limit_headers(resp)


def test_shared_daily_budget_endpoint_with_limiter_enabled(
    api_client, clean_db, org_a, rate_limiting_enabled
):
    """Stacked @limiter.limit + shared daily budget on a Pydantic endpoint."""
    client_id = seed_client(clean_db, org_a.org_id, "Alan Partridge")
    resp = api_client.post(
        f"/api/monitor/clients/{client_id}/review-note",
        headers=auth_headers_for(org_a),
    )
    # LLM is unconfigured in tests: the deterministic fallback still returns 200.
    assert resp.status_code == 200, resp.text
    _assert_rate_limit_headers(resp)


def test_response_returning_endpoint_with_limiter_enabled(
    api_client, clean_db, org_a, rate_limiting_enabled
):
    """CSV export returns a real Response; headers inject onto it directly."""
    resp = api_client.get(
        "/api/monitor/export?type=clients", headers=auth_headers_for(org_a)
    )
    assert resp.status_code == 200
    _assert_rate_limit_headers(resp)


def test_every_decorated_endpoint_declares_a_response_param():
    """Static guard: any endpoint wearing a limiter decorator must either take
    a ``response: Response`` param or return a Response subclass — otherwise
    slowapi's header injection crashes at runtime (only with limits enabled,
    so a runtime test of every route is easy to miss)."""
    import inspect
    import typing

    from fastapi.responses import Response as FastAPIResponse

    from app.main import app

    offenders = []
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        # slowapi wraps endpoints with functools.wraps; unwrap to the original.
        wrapped = inspect.unwrap(endpoint)
        if wrapped is endpoint:
            continue  # not decorated
        # Routers use `from __future__ import annotations`, so resolve the
        # stringified hints against the function's module globals.
        try:
            hints = typing.get_type_hints(wrapped)
        except Exception:
            hints = {}
        has_response_param = any(
            isinstance(hint, type) and issubclass(hint, FastAPIResponse)
            for name, hint in hints.items()
            if name != "return"
        )
        return_hint = hints.get("return")
        returns_response = isinstance(return_hint, type) and issubclass(
            return_hint, FastAPIResponse
        )
        # export_csv returns a Response instance without annotating it.
        known_response_returners = {"export_csv"}
        if not (has_response_param or returns_response or wrapped.__name__ in known_response_returners):
            offenders.append(f"{route.path} ({wrapped.__name__})")
    assert offenders == [], (
        "Rate-limited endpoints missing a `response: Response` parameter "
        f"(slowapi header injection will 500 in production): {offenders}"
    )
