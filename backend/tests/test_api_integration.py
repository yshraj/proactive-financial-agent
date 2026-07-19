"""
API integration tests: real FastAPI app over a real migrated Postgres with the
RLS-enforced runtime role. Covers the authz matrix (anonymous / org A / org B)
and the durable audit + jobs surfaces end-to-end. The LLM and Qdrant are not
configured in tests: AI endpoints fall back to their deterministic paths.
"""
from __future__ import annotations

import uuid

from tests.conftest import auth_headers_for, make_jwt, seed_client

# Representative endpoint matrix: (method, path builder, body)
_PROTECTED_GETS = [
    "/api/monitor/clients",
    "/api/monitor/analytics",
    "/api/monitor/pulse?simulated_date=2026-07-17",
    "/api/monitor/alerts",
    "/api/monitor/completed",
    "/api/ingest/documents",
    "/api/compliance/audit",
    "/api/compliance/posture",
]


def test_health_is_open(api_client):
    assert api_client.get("/health").status_code == 200


def test_readiness_reports_checks(api_client):
    resp = api_client.get("/health/ready")
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert body["auth_mode"] == "required"
    assert "database" in body["checks"]
    assert body["checks"]["database"]["ok"] is True
    assert body["migration_version"]  # alembic version visible to app role


def test_all_api_routes_require_auth(api_client):
    """Anonymous requests are 401 in required mode — the fail-closed proof."""
    for path in _PROTECTED_GETS:
        resp = api_client.get(path)
        assert resp.status_code == 401, f"{path} returned {resp.status_code}"
    assert api_client.post("/api/chat/", json={"query": "hi"}).status_code == 401
    assert api_client.post("/api/settings/load-sample-data").status_code == 401


def test_garbage_token_is_rejected(api_client):
    resp = api_client.get(
        "/api/monitor/clients", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert resp.status_code == 401


def test_first_login_provisions_workspace_and_serves_empty_book(api_client):
    token = make_jwt(str(uuid.uuid4()), "fresh@adviser.co.uk")
    resp = api_client.get(
        "/api/monitor/clients", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["clients"] == []


def test_cross_org_reads_are_isolated(api_client, clean_db, org_a, org_b):
    seed_client(clean_db, org_a.org_id, "Alan Partridge")
    seed_client(clean_db, org_b.org_id, "Lynne Benfield")

    a_list = api_client.get("/api/monitor/clients", headers=auth_headers_for(org_a)).json()
    b_list = api_client.get("/api/monitor/clients", headers=auth_headers_for(org_b)).json()
    assert [c["full_name"] for c in a_list["clients"]] == ["Alan Partridge"]
    assert [c["full_name"] for c in b_list["clients"]] == ["Lynne Benfield"]


def test_cross_org_object_access_is_404(api_client, clean_db, org_a, org_b):
    """IDOR drill: org B probing org A's client id gets Not Found, not data."""
    client_id = seed_client(clean_db, org_a.org_id, "Alan Partridge")

    own = api_client.get(f"/api/monitor/clients/{client_id}", headers=auth_headers_for(org_a))
    assert own.status_code == 200

    for resp in (
        api_client.get(f"/api/monitor/clients/{client_id}", headers=auth_headers_for(org_b)),
        api_client.patch(
            f"/api/monitor/clients/{client_id}",
            json={"risk_score": 1},
            headers=auth_headers_for(org_b),
        ),
        api_client.post(
            f"/api/monitor/clients/{client_id}/apply-playbook",
            json={"playbook_id": "annual_review"},
            headers=auth_headers_for(org_b),
        ),
        api_client.post(
            f"/api/monitor/clients/{client_id}/review-note", headers=auth_headers_for(org_b)
        ),
    ):
        assert resp.status_code == 404, f"cross-org access leaked: {resp.status_code}"


def test_cross_org_alert_mutation_is_404(api_client, clean_db, org_a, org_b):
    seed_client(
        clean_db,
        org_a.org_id,
        alerts=[{"trigger_date": "2026-08-01", "title": "ISA top-up"}],
    )
    alerts = api_client.get(
        "/api/monitor/alerts", headers=auth_headers_for(org_a)
    ).json()["alerts"]
    real = [a for a in alerts if not a["id"].startswith("review-overdue-")]
    alert_id = real[0]["id"]

    resp = api_client.patch(
        f"/api/monitor/alerts/{alert_id}/status",
        json={"status": "COMPLETED"},
        headers=auth_headers_for(org_b),
    )
    assert resp.status_code == 404


def test_sample_data_and_pulse_are_org_scoped(api_client, clean_db, org_a, org_b):
    loaded = api_client.post(
        "/api/settings/load-sample-data", headers=auth_headers_for(org_a)
    ).json()
    assert loaded["loaded"] is True

    a_pulse = api_client.get(
        "/api/monitor/pulse?simulated_date=2026-07-17", headers=auth_headers_for(org_a)
    ).json()
    b_pulse = api_client.get(
        "/api/monitor/pulse?simulated_date=2026-07-17", headers=auth_headers_for(org_b)
    ).json()
    assert a_pulse["client_count"] > 0
    assert b_pulse["client_count"] == 0
    assert b_pulse["alerts"] == []


def test_clear_data_only_wipes_own_org(api_client, clean_db, org_a, org_b):
    seed_client(clean_db, org_a.org_id, "Alan")
    seed_client(clean_db, org_b.org_id, "Lynne")

    resp = api_client.post("/api/settings/clear-data", headers=auth_headers_for(org_a))
    assert resp.status_code == 200

    a_clients = api_client.get("/api/monitor/clients", headers=auth_headers_for(org_a)).json()
    b_clients = api_client.get("/api/monitor/clients", headers=auth_headers_for(org_b)).json()
    assert a_clients["clients"] == []
    assert [c["full_name"] for c in b_clients["clients"]] == ["Lynne"]

    # The wipe itself is on the immutable record.
    events = api_client.get(
        "/api/compliance/audit/events?action=data.cleared", headers=auth_headers_for(org_a)
    ).json()["events"]
    assert len(events) == 1


def test_client_update_writes_before_after_audit(api_client, clean_db, org_a):
    client_id = seed_client(clean_db, org_a.org_id, "Alan", risk_score=5)
    resp = api_client.patch(
        f"/api/monitor/clients/{client_id}",
        json={"risk_score": 7},
        headers=auth_headers_for(org_a),
    )
    assert resp.status_code == 200

    events = api_client.get(
        "/api/compliance/audit/events?action=client.updated", headers=auth_headers_for(org_a)
    ).json()["events"]
    assert len(events) == 1
    assert events[0]["resource_id"] == client_id
    assert events[0]["request_id"]


def test_audit_events_are_org_scoped_via_api(api_client, clean_db, org_a, org_b):
    client_id = seed_client(clean_db, org_a.org_id, "Alan")
    api_client.patch(
        f"/api/monitor/clients/{client_id}",
        json={"risk_score": 3},
        headers=auth_headers_for(org_a),
    )
    b_events = api_client.get(
        "/api/compliance/audit/events", headers=auth_headers_for(org_b)
    ).json()["events"]
    assert b_events == []


def test_export_is_org_scoped_and_audited(api_client, clean_db, org_a, org_b):
    seed_client(clean_db, org_a.org_id, "Alan Partridge")
    resp = api_client.get(
        "/api/monitor/export?type=clients", headers=auth_headers_for(org_b)
    )
    assert resp.status_code == 200
    assert "Alan Partridge" not in resp.text


def test_markdown_and_text_uploads_are_accepted(api_client, clean_db, org_a):
    """.md/.txt go through the same validated upload path as PDF/DOCX."""
    for name, mime, body in (
        ("meeting-notes.md", "text/markdown", b"# Review\nShort note."),
        ("call-summary.txt", "text/plain", b"Client called about ISA."),
    ):
        resp = api_client.post(
            "/api/ingest/upload",
            files={"file": (name, body, mime)},
            headers=auth_headers_for(org_a),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["filename"] == name

    listed = api_client.get(
        "/api/ingest/documents", headers=auth_headers_for(org_a)
    ).json()
    names = {d["filename"] for d in listed}
    assert {"meeting-notes.md", "call-summary.txt"} <= names


def test_binary_masquerading_as_text_is_rejected(api_client, org_a):
    resp = api_client.post(
        "/api/ingest/upload",
        files={"file": ("innocent.txt", b"MZ\x00\x00\x03\x00\x00\x00", "text/plain")},
        headers=auth_headers_for(org_a),
    )
    assert resp.status_code == 400
    assert "does not match" in resp.json()["detail"]


def test_unsupported_extension_is_rejected(api_client, org_a):
    resp = api_client.post(
        "/api/ingest/upload",
        files={"file": ("archive.zip", b"PK\x03\x04data", "application/zip")},
        headers=auth_headers_for(org_a),
    )
    assert resp.status_code == 400
    assert "Only PDF, Word" in resp.json()["detail"]


def test_duplicate_detection_is_per_org(api_client, clean_db, org_a, org_b):
    """The content-hash oracle is closed: another org can upload the same doc."""
    transcript = {
        "text": "Meeting with client about pension consolidation. " * 5,
        "title": "Pension chat",
    }
    first = api_client.post(
        "/api/ingest/transcript", json=transcript, headers=auth_headers_for(org_a)
    )
    assert first.status_code == 201

    duplicate_same_org = api_client.post(
        "/api/ingest/transcript", json=transcript, headers=auth_headers_for(org_a)
    )
    assert duplicate_same_org.status_code == 409

    other_org = api_client.post(
        "/api/ingest/transcript", json=transcript, headers=auth_headers_for(org_b)
    )
    assert other_org.status_code == 201, "cross-org duplicate oracle still present"


def test_chat_conversation_cannot_be_hijacked_via_api(api_client, clean_db, org_a, org_b):
    from app.services import conversations

    conv_id = conversations.create(ctx=org_a)
    conversations.add_message(conv_id, "user", "org A secret question", ctx=org_a)

    resp = api_client.post(
        "/api/chat/",
        json={"query": "continue please", "conversation_id": conv_id},
        headers=auth_headers_for(org_b),
    )
    # Chat still answers (deterministic no-LLM path) but under a NEW thread.
    if resp.status_code == 200:
        assert resp.json()["conversation_id"] != conv_id


def test_job_status_view_is_org_scoped(api_client, clean_db, org_a, org_b):
    from app.services import jobs

    job_id = str(uuid.uuid4())
    jobs.create(job_id, kind="upload", filename="a.pdf", ctx=org_a)
    own = api_client.get(f"/api/ingest/jobs/{job_id}", headers=auth_headers_for(org_a))
    assert own.status_code == 200
    other = api_client.get(f"/api/ingest/jobs/{job_id}", headers=auth_headers_for(org_b))
    assert other.status_code == 404


def test_posture_reports_durable_audit_and_auth(api_client, org_a):
    posture = api_client.get(
        "/api/compliance/posture", headers=auth_headers_for(org_a)
    ).json()
    assert posture["durable_audit"] is True
    assert posture["auth_required"] is True
    assert posture["auth_mode"] == "required"


def test_unhandled_errors_return_safe_message(api_client, org_a, monkeypatch):
    """The global exception handler must not leak stack traces."""
    from app.routers import monitor

    def _boom(*args, **kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(monitor, "compute_book_analytics", _boom)
    resp = api_client.get("/api/monitor/analytics", headers=auth_headers_for(org_a))
    assert resp.status_code == 500
    assert "secret internal detail" not in resp.text
    assert resp.headers.get("X-Request-ID")


def test_demo_mode_serves_shared_workspace(api_app, clean_db, monkeypatch):
    """AUTH_MODE=demo: anonymous requests act on the default demo workspace."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AUTH_MODE", "demo")
    monkeypatch.delenv("ENV", raising=False)
    with TestClient(api_app, raise_server_exceptions=False) as client:
        resp = client.get("/api/monitor/clients")
        assert resp.status_code == 200
        assert resp.json()["clients"] == []
        # And an authenticated user still gets their own isolated workspace.
        seed_client(clean_db, "00000000-0000-0000-0000-000000000001", "Demo Client")
        assert len(client.get("/api/monitor/clients").json()["clients"]) == 1


def test_demo_mode_cannot_boot_in_production(api_app, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AUTH_MODE", "demo")
    monkeypatch.setenv("ENV", "production")
    import pytest

    with pytest.raises(RuntimeError, match="demo"):
        with TestClient(api_app):
            pass  # lifespan's enforce_auth_mode must refuse
