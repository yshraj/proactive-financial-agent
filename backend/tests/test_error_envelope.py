"""Structured error envelope: every API error carries
{"error": {"code", "message", "retryable"}} alongside the legacy "detail",
with friendly copy and no leaked internals (SQL, provider errors, paths).
"""
from __future__ import annotations

import pytest

from tests.conftest import auth_headers_for


def _envelope(resp) -> dict:
    body = resp.json()
    assert "error" in body, body
    env = body["error"]
    assert set(env) == {"code", "message", "retryable"}, env
    assert isinstance(env["retryable"], bool)
    return env


def test_unknown_route_404_has_envelope(api_client):
    resp = api_client.get("/api/definitely-not-a-route", headers={})
    assert resp.status_code == 404
    env = _envelope(resp)
    assert env["code"] == "not_found"
    assert env["retryable"] is False
    assert resp.json()["detail"] == "Not Found"


def test_unauthenticated_401_is_friendly(api_client):
    resp = api_client.post("/api/chat/", json={"query": "hi"})
    assert resp.status_code == 401
    env = _envelope(resp)
    assert env["code"] == "unauthorized"
    assert "sign in" in env["message"].lower()
    assert resp.headers.get("www-authenticate") == "Bearer"


def test_validation_422_keeps_field_details_and_adds_envelope(api_client, org_a):
    resp = api_client.post(
        "/api/chat/", headers=auth_headers_for(org_a), json={"query": ["not", "a", "string"]}
    )
    assert resp.status_code == 422
    env = _envelope(resp)
    assert env["code"] == "validation_error"
    assert env["message"] == "Some fields are invalid. Please review and try again."
    assert isinstance(resp.json()["detail"], list)  # FastAPI field errors kept


def test_unsupported_upload_type_400(api_client, clean_db, org_a):
    resp = api_client.post(
        "/api/ingest/upload-async",
        files={"file": ("virus.exe", b"MZ\x90\x00", "application/octet-stream")},
        headers=auth_headers_for(org_a),
    )
    assert resp.status_code == 400
    env = _envelope(resp)
    assert env["code"] == "invalid_request"
    assert "Only PDF, Word" in env["message"]


def test_oversized_upload_413_copy_and_code(api_client, clean_db, org_a, monkeypatch):
    from app.routers import ingest

    monkeypatch.setattr(ingest, "MAX_UPLOAD_BYTES", 1024)  # 1 KB for the test
    resp = api_client.post(
        "/api/ingest/upload-async",
        files={"file": ("big.md", b"x" * 4096, "text/markdown")},
        headers=auth_headers_for(org_a),
    )
    assert resp.status_code == 413
    env = _envelope(resp)
    assert env["code"] == "upload_too_large"
    assert env["retryable"] is False
    assert "exceeds the current upload limit (1 MB)" in env["message"]
    assert "Larger file support is coming soon." in resp.json()["detail"]


def test_upload_limits_endpoint(api_client, clean_db, org_a):
    resp = api_client.get("/api/ingest/limits", headers=auth_headers_for(org_a))
    assert resp.status_code == 200
    body = resp.json()
    assert body["max_upload_bytes"] > 0
    assert body["max_upload_mb"] == body["max_upload_bytes"] // (1024 * 1024)
    assert ".pdf" in body["allowed_extensions"]


def test_duplicate_upload_409_keeps_detail_dict_and_maps_code(api_client, clean_db, org_a, monkeypatch):
    from app.routers.ingest import IngestOutcome

    monkeypatch.setattr(
        "app.routers.ingest.run_dual_path_ingestion_from_storage",
        lambda *a, **k: IngestOutcome(),
    )
    files = {"file": ("note.md", b"# Note\nPension discussed today at length.", "text/markdown")}
    first = api_client.post(
        "/api/ingest/upload-async", files=files, headers=auth_headers_for(org_a)
    )
    assert first.status_code == 202, first.text
    dup = api_client.post(
        "/api/ingest/upload-async", files=files, headers=auth_headers_for(org_a)
    )
    assert dup.status_code == 409
    env = _envelope(dup)
    assert env["code"] == "duplicate"
    assert dup.json()["detail"]["code"] == "DUPLICATE"  # legacy dict preserved
    assert dup.json()["detail"]["existing_filename"] == "note.md"


def test_llm_outage_returns_clean_503(api_client, clean_db, org_a, monkeypatch):
    """The provider stack being down must never leak text — fixed copy, 503."""
    from app.services.llm import AIUnavailableError
    from app.routers import chat as chat_router

    def boom(**kwargs):
        raise AIUnavailableError(
            "We couldn't generate AI results right now. Please try again in a few minutes."
        )

    monkeypatch.setattr(chat_router, "retrieve_for_chat", lambda *a, **k: ("", []))
    monkeypatch.setattr(chat_router, "complete_with_system_ex", boom)
    resp = api_client.post(
        "/api/chat/", headers=auth_headers_for(org_a), json={"query": "What changed?"}
    )
    assert resp.status_code == 503
    env = _envelope(resp)
    assert env["code"] == "ai_unavailable"
    assert env["retryable"] is True
    assert env["message"] == (
        "We couldn't generate AI results right now. Please try again in a few minutes."
    )


def test_llm_provider_error_text_never_reaches_client(api_client, clean_db, org_a, monkeypatch):
    """End to end through llm.complete and the real gateway routing loop: a
    provider 500 whose body contains secrets must be wrapped into fixed copy."""
    import httpx

    from app.services import model_gateway

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500, json={"error": "openai.APIConnectionError: host sk-secret leaked"}
        )

    monkeypatch.setenv("GROQ_API_KEY", "gsk-test-key")
    monkeypatch.setenv("LLM_QUOTA_BACKEND", "memory")
    model_gateway.reset_for_tests()
    model_gateway.set_transport_factory_for_tests(lambda: httpx.MockTransport(handler))
    try:
        monkeypatch.setattr("app.routers.chat.retrieve_for_chat", lambda *a, **k: ("", []))
        resp = api_client.post(
            "/api/chat/", headers=auth_headers_for(org_a), json={"query": "What changed?"}
        )
    finally:
        model_gateway.set_transport_factory_for_tests(None)
        model_gateway.reset_for_tests()
    assert resp.status_code == 503
    assert "sk-secret" not in resp.text
    assert "APIConnectionError" not in resp.text
    assert _envelope(resp)["code"] == "ai_unavailable"


def test_vector_search_outage_returns_clean_503(api_client, clean_db, org_a, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("qdrant cluster https://xyz.cloud.qdrant.io unreachable")

    monkeypatch.setattr("app.routers.chat.retrieve_for_chat", boom)
    resp = api_client.post(
        "/api/chat/", headers=auth_headers_for(org_a), json={"query": "What changed?"}
    )
    assert resp.status_code == 503
    env = _envelope(resp)
    assert env["code"] == "service_unavailable"
    assert env["message"] == "Search is temporarily unavailable. Please try again shortly."
    assert "qdrant" not in resp.text.lower()


def test_rate_limit_envelope_and_retry_after(api_client, clean_db, org_a, monkeypatch):
    from app import security

    monkeypatch.setattr(security.limiter, "enabled", True)
    last = None
    for _ in range(40):  # compliance scan allows 30/minute, no external deps
        last = api_client.post(
            "/api/compliance/scan",
            headers=auth_headers_for(org_a),
            json={"text": "Client mentioned fees felt unclear."},
        )
        if last.status_code == 429:
            break
    assert last is not None and last.status_code == 429
    env = _envelope(last)
    assert env["code"] == "rate_limited"
    assert env["retryable"] is True
    assert env["message"] == "Too many requests. Please wait a moment and try again."
    assert "Retry-After" in last.headers


@pytest.mark.parametrize(
    "context, must_not_contain",
    [
        ("ingest_persist", "psycopg2"),
        ("ingest_vector", "qdrant"),
        ("ai_unavailable", "openai"),
        ("search_unavailable", "cluster"),
        ("job_failed", "traceback"),
    ],
)
def test_public_error_messages_are_fixed_copy(context, must_not_contain):
    from app.services.safety import public_error_message

    msg = public_error_message(context)
    assert must_not_contain.lower() not in msg.lower()
    assert msg.endswith((".", "…"))
