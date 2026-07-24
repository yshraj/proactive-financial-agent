"""Regenerate (refresh=true) bypasses the brief / draft-email response caches."""
from __future__ import annotations

from tests.conftest import auth_headers_for, fake_gateway_result, seed_client

def test_brief_refresh_bypasses_cache(api_client, clean_db, org_a, monkeypatch):
    client_id = seed_client(clean_db, org_a.org_id, "Alan Partridge")
    calls = {"n": 0}

    def fake_complete(**kwargs):
        calls["n"] += 1
        return fake_gateway_result(
            f"Brief version {calls['n']}\n---TALKING_POINTS---\nPoint one", purpose="brief"
        )

    monkeypatch.setattr("app.routers.chat.complete_with_system_ex", fake_complete)
    monkeypatch.setattr(
        "app.routers.chat.retrieve_for_brief", lambda *a, **k: ("", [])
    )

    headers = auth_headers_for(org_a)
    first = api_client.post("/api/chat/brief", json={"client_id": client_id}, headers=headers)
    assert first.json()["brief"] == "Brief version 1"

    # Without refresh: served from cache, the LLM is not called again.
    cached = api_client.post("/api/chat/brief", json={"client_id": client_id}, headers=headers)
    assert cached.json()["brief"] == "Brief version 1"
    assert calls["n"] == 1

    # Regenerate: bypasses the cache and re-populates it.
    fresh = api_client.post(
        "/api/chat/brief", json={"client_id": client_id, "refresh": True}, headers=headers
    )
    assert fresh.json()["brief"] == "Brief version 2"
    after = api_client.post("/api/chat/brief", json={"client_id": client_id}, headers=headers)
    assert after.json()["brief"] == "Brief version 2"
    assert calls["n"] == 2


def test_draft_email_refresh_bypasses_cache(api_client, clean_db, org_a, monkeypatch):
    seed_client(
        clean_db,
        org_a.org_id,
        "Alan Partridge",
        alerts=[{"trigger_date": "2026-08-01", "title": "ISA top-up"}],
    )
    headers = auth_headers_for(org_a)
    alerts = api_client.get("/api/monitor/alerts", headers=headers).json()["alerts"]
    alert_id = next(a["id"] for a in alerts if not a["id"].startswith("review-overdue-"))

    calls = {"n": 0}

    def fake_complete(**kwargs):
        calls["n"] += 1
        return fake_gateway_result(f"Draft version {calls['n']}", purpose="draft")

    monkeypatch.setattr("app.routers.monitor.complete_with_system_ex", fake_complete)

    first = api_client.post("/api/monitor/draft-email", json={"alert_id": alert_id}, headers=headers)
    assert first.json()["draft"] == "Draft version 1"
    cached = api_client.post("/api/monitor/draft-email", json={"alert_id": alert_id}, headers=headers)
    assert cached.json()["draft"] == "Draft version 1"
    fresh = api_client.post(
        "/api/monitor/draft-email", json={"alert_id": alert_id, "refresh": True}, headers=headers
    )
    assert fresh.json()["draft"] == "Draft version 2"
    assert calls["n"] == 2
