from __future__ import annotations

import pytest

from tests.conftest import auth_headers_for


def test_lazy_summary_starts_with_lifetime_balance(clean_db, org_a, monkeypatch):
    from app.services import credits

    monkeypatch.setenv("DEFAULT_LIFETIME_CREDITS", "50")
    summary = credits.get_summary(ctx=org_a)
    assert summary["total_granted"] == 50
    assert summary["used"] == 0
    assert summary["remaining"] == 50
    assert summary["costs"]["chat"] == 1


def test_reserve_commit_release_and_idempotency(clean_db, org_a):
    from app.services import credits

    first = credits.reserve(credits.CreditFeature.CHAT, "chat:one", ctx=org_a)
    assert credits.get_summary(ctx=org_a)["remaining"] == 49
    with pytest.raises(credits.DuplicateCreditAction) as held:
        credits.reserve(credits.CreditFeature.CHAT, "chat:one", ctx=org_a)
    assert held.value.status == "reserved"
    assert credits.commit(first.id, ctx=org_a) == "committed"
    assert credits.commit(first.id, ctx=org_a) == "committed"

    with pytest.raises(credits.DuplicateCreditAction) as duplicate:
        credits.reserve(credits.CreditFeature.CHAT, "chat:one", ctx=org_a)
    assert duplicate.value.status == "committed"
    assert credits.get_summary(ctx=org_a)["used"] == 1

    second = credits.reserve(credits.CreditFeature.REPORT, "report:two", ctx=org_a)
    assert credits.release(second.id, ctx=org_a) == "released"
    assert credits.release(second.id, ctx=org_a) == "released"
    summary = credits.get_summary(ctx=org_a)
    assert summary["used"] == 1
    assert summary["remaining"] == 49
    usage = credits.get_history(ctx=org_a)["entries"][0]
    assert usage["delta"] == -1
    assert usage["balance_after"] == 49


def test_released_idempotency_key_cannot_start_another_action(clean_db, org_a):
    from app.services import credits

    reservation = credits.reserve(
        credits.CreditFeature.CHAT, "chat:released", ctx=org_a
    )
    credits.release(reservation.id, ctx=org_a)
    with pytest.raises(credits.DuplicateCreditAction) as duplicate:
        credits.reserve(credits.CreditFeature.CHAT, "chat:released", ctx=org_a)
    assert duplicate.value.status == "released"
    assert credits.get_summary(ctx=org_a)["used"] == 0


def test_insufficient_balance_never_goes_negative(clean_db, org_a, monkeypatch):
    from app.services import credits

    monkeypatch.setenv("DEFAULT_LIFETIME_CREDITS", "2")
    with pytest.raises(credits.InsufficientCredits) as caught:
        credits.reserve(credits.CreditFeature.REPORT, "too-expensive", ctx=org_a)
    assert caught.value.required == 5
    assert caught.value.remaining == 2
    assert credits.get_summary(ctx=org_a)["remaining"] == 2


def test_user_and_tenant_accounts_are_isolated(clean_db, org_a, org_b):
    from app.context import TenantContext
    from app.services import credits

    reservation = credits.reserve(credits.CreditFeature.CHAT, "isolated", ctx=org_a)
    credits.commit(reservation.id, ctx=org_a)
    assert credits.get_summary(ctx=org_a)["used"] == 1
    assert credits.get_summary(ctx=org_b)["used"] == 0

    org_fallback = TenantContext(org_id=org_a.org_id, user_id=None, role="service")
    assert credits.get_summary(ctx=org_fallback)["used"] == 0


def test_history_and_manual_request_api(api_client, org_a, monkeypatch):
    monkeypatch.setenv("CREDIT_CONTACT_EMAIL", "credits@example.test")
    headers = auth_headers_for(org_a)

    summary = api_client.get("/api/credits", headers=headers)
    assert summary.status_code == 200
    assert summary.json() == {
        "total_granted": 50,
        "used": 0,
        "remaining": 50,
        "version": 1,
        "costs": {
            "chat": 1,
            "report": 5,
            "image": 3,
            "pdf_analysis": 2,
            "deep_research": 10,
            "draft_email": 2,
            "digest": 2,
            "review_note": 3,
            "client_summary": 1,
            "transcript_analysis": 2,
        },
        "contact": {
            "email": "credits@example.test",
            "request_enabled": True,
        },
    }

    requested = api_client.post(
        "/api/credits/requests",
        headers=headers,
        json={"message": "Please review our account."},
    )
    assert requested.status_code == 202
    assert requested.json()["status"] == "pending"

    history = api_client.get("/api/credits/history?limit=10", headers=headers)
    assert history.status_code == 200
    payload = history.json()
    assert set(payload) == {"entries", "total", "limit", "offset"}
    assert payload["total"] == 1
    assert payload["limit"] == 10
    assert payload["offset"] == 0
    entry = payload["entries"][0]
    assert set(entry) == {
        "id",
        "created_at",
        "feature",
        "delta",
        "balance_after",
        "status",
        "description",
    }
    assert entry["feature"] == "initial_allocation"
    assert entry["delta"] == 50
    assert entry["balance_after"] == 50
    assert entry["status"] == "committed"


def test_chat_endpoint_is_guarded_and_retry_is_not_double_charged(
    api_client, org_a, monkeypatch
):
    from app.routers import chat

    monkeypatch.setattr(chat, "_get_structured_context", lambda ctx, client_id=None: "Book")
    monkeypatch.setattr(chat, "retrieve_for_chat", lambda *args, **kwargs: ("", []))
    calls = []

    def complete(**kwargs):
        calls.append(kwargs)
        return "A guarded answer."

    monkeypatch.setattr(chat, "complete_with_system", complete)
    headers = {
        **auth_headers_for(org_a),
        "X-Idempotency-Key": "chat-action-1",
    }
    first = api_client.post("/api/chat/", headers=headers, json={"query": "What changed?"})
    assert first.status_code == 200
    assert len(calls) == 1

    retry = api_client.post("/api/chat/", headers=headers, json={"query": "What changed?"})
    assert retry.status_code == 409
    assert retry.json() == {
        "error": "duplicate_credit_action",
        "feature": "chat",
        "status": "committed",
        "detail": "This idempotent AI action has already been processed.",
    }
    assert len(calls) == 1
    summary = api_client.get("/api/credits", headers=auth_headers_for(org_a)).json()
    assert summary["used"] == 1


def test_guarded_chat_returns_structured_insufficient_error_without_inference(
    api_client, org_a, monkeypatch
):
    from app.routers import chat

    monkeypatch.setenv("DEFAULT_LIFETIME_CREDITS", "0")
    called = []
    monkeypatch.setattr(
        chat, "complete_with_system", lambda **kwargs: called.append(kwargs)
    )
    response = api_client.post(
        "/api/chat/",
        headers=auth_headers_for(org_a),
        json={"query": "Should never reach inference"},
    )
    assert response.status_code == 409
    assert response.json() == {
        "error": "insufficient_credits",
        "required": 1,
        "remaining": 0,
        "feature": "chat",
        "contact_available": True,
    }
    assert called == []


def test_grant_first_operation_includes_default_and_records_balances(
    clean_db, org_a, monkeypatch
):
    from app.services import credits

    monkeypatch.setenv("DEFAULT_LIFETIME_CREDITS", "50")
    credits.grant(
        50,
        "manual-grant-1",
        metadata={"description": "Support-approved top-up"},
        ctx=org_a,
    )
    assert credits.get_summary(ctx=org_a)["total_granted"] == 100
    history = credits.get_history(ctx=org_a)["entries"]
    assert [(entry["delta"], entry["balance_after"]) for entry in history] == [
        (50, 100),
        (50, 50),
    ]


def test_credit_balance_unavailable_has_structured_shape(
    api_client, org_a, monkeypatch
):
    from app.routers import credits as credits_router
    from app.services.credits import CreditBalanceUnavailable

    def unavailable(*args, **kwargs):
        raise CreditBalanceUnavailable("offline")

    monkeypatch.setattr(credits_router.credits, "get_summary", unavailable)
    response = api_client.get("/api/credits", headers=auth_headers_for(org_a))
    assert response.status_code == 503
    assert response.json() == {
        "error": "credit_balance_unavailable",
        "detail": "Credit balance is temporarily unavailable. Please try again.",
    }


def test_passive_digest_does_not_infer_or_charge(api_client, org_a, monkeypatch):
    from app.routers import monitor

    provider_calls = []

    def generate(*args, **kwargs):
        provider_calls.append((args, kwargs))
        return "Generated digest"

    monkeypatch.setattr(monitor, "_generate_morning_digest", generate)
    headers = auth_headers_for(org_a)
    passive = api_client.get(
        "/api/monitor/digest?simulated_date=2026-07-20",
        headers=headers,
    )
    assert passive.status_code == 200
    assert provider_calls == []
    assert api_client.get("/api/credits", headers=headers).json()["used"] == 0

    generated = api_client.get(
        "/api/monitor/digest?simulated_date=2026-07-20&refresh=true",
        headers={**headers, "X-Idempotency-Key": "digest-refresh-1"},
    )
    assert generated.status_code == 200
    assert generated.json()["digest"] == "Generated digest"
    assert len(provider_calls) == 1
    assert api_client.get("/api/credits", headers=headers).json()["used"] == 2
