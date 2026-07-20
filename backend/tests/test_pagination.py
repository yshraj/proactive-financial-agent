"""Phase 5 — list endpoints are bounded regardless of query params.

/clients and /alerts must never return an unbounded result set: limit is
clamped to 200 server-side, and total reflects the full count for page controls.
"""
from __future__ import annotations

from datetime import date

from tests.conftest import auth_headers_for, seed_client


def _seed_clients(clean_db, org_id, n):
    for i in range(n):
        seed_client(clean_db, org_id, full_name=f"Client {i:03d}")


def test_clients_default_page_and_total(api_client, clean_db, org_a):
    _seed_clients(clean_db, org_a.org_id, 3)
    body = api_client.get("/api/monitor/clients", headers=auth_headers_for(org_a)).json()
    assert body["total"] == 3
    assert len(body["clients"]) == 3


def test_clients_limit_and_offset(api_client, clean_db, org_a):
    _seed_clients(clean_db, org_a.org_id, 5)
    first = api_client.get(
        "/api/monitor/clients?limit=2&offset=0", headers=auth_headers_for(org_a)
    ).json()
    assert first["total"] == 5
    assert len(first["clients"]) == 2

    second = api_client.get(
        "/api/monitor/clients?limit=2&offset=2", headers=auth_headers_for(org_a)
    ).json()
    assert len(second["clients"]) == 2
    # Ordered by name, so pages don't overlap.
    assert {c["id"] for c in first["clients"]}.isdisjoint(
        {c["id"] for c in second["clients"]}
    )


def test_clients_limit_is_clamped_not_rejected(api_client, clean_db, org_a):
    _seed_clients(clean_db, org_a.org_id, 3)
    # An absurd limit is clamped to the 200 ceiling and still returns results.
    res = api_client.get(
        "/api/monitor/clients?limit=100000", headers=auth_headers_for(org_a)
    )
    assert res.status_code == 200
    assert len(res.json()["clients"]) == 3  # all 3, bounded by the ceiling


def test_alerts_are_paginated(api_client, clean_db, org_a):
    today = date.today().isoformat()
    for i in range(4):
        seed_client(
            clean_db,
            org_a.org_id,
            full_name=f"Alerty {i}",
            alerts=[{"trigger_date": today, "type": "DEADLINE", "priority": "HIGH", "title": f"A{i}"}],
        )
    body = api_client.get(
        f"/api/monitor/alerts?simulated_date={today}&days=30&limit=2",
        headers=auth_headers_for(org_a),
    ).json()
    assert body["total"] >= 4
    assert len(body["alerts"]) == 2


def test_alerts_limit_clamped(api_client, clean_db, org_a):
    today = date.today().isoformat()
    seed_client(
        clean_db,
        org_a.org_id,
        full_name="Solo",
        alerts=[{"trigger_date": today, "type": "DEADLINE", "priority": "HIGH", "title": "x"}],
    )
    res = api_client.get(
        f"/api/monitor/alerts?simulated_date={today}&limit=100000",
        headers=auth_headers_for(org_a),
    )
    assert res.status_code == 200
    assert len(res.json()["alerts"]) <= 200
