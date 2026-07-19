"""
Duplicate protection across ingestion (the md-vs-pdf bug class):

1. identical text in a different file format links to the existing records
   instead of creating a second client + alert set;
2. a new document about an existing client merges (updates non-null fields)
   rather than duplicating the client;
3. alert inserts anti-join, so retries and same-client documents never
   duplicate an open alert;
4. regenerate flags bypass the brief/draft response caches.

The LLM is faked (deterministic extraction) and Qdrant indexing is a no-op,
so these run offline against the real migrated Postgres.
"""
from __future__ import annotations

import uuid

import pytest

from tests.conftest import auth_headers_for, seed_client

# Long enough to clear the 50-char short-circuit in extract_structured_from_text.
FACT_FIND_TEXT = (
    "CLIENT PROFILE: MARGARET & JAMES WHITFIELD. Net worth 1,240,000. "
    "Pending: Bed & ISA confirmation. Next review 05/08/2026."
)


@pytest.fixture()
def fake_ai(monkeypatch):
    """Deterministic extraction + no-op vector indexing."""

    def fake_extract(text: str):
        return {
            "client": {
                "full_name": "Margaret & James Whitfield",
                "risk_score": 5,
                "total_assets": 1_240_000,
                "last_review_date": "2025-06-10",
            },
            "alerts": [
                {
                    "trigger_date": "2025-07-10",
                    "type": "FOLLOW_UP",
                    "priority": "MEDIUM",
                    "title": "Bed & ISA Confirmation",
                    "description": "Awaiting client decision.",
                },
                {
                    "trigger_date": "2026-08-05",
                    "type": "DEADLINE",
                    "priority": "HIGH",
                    "title": "Next review due",
                    "description": "Annual review.",
                },
            ],
            "raw_text": text,
        }

    monkeypatch.setattr(
        "app.services.llm_extractor.extract_structured_from_text", fake_extract
    )
    monkeypatch.setattr(
        "app.routers.ingest.vector_store.index_document_text",
        lambda **kwargs: None,
    )
    return fake_extract


def _upload(api_client, org, name: str, body: bytes, mime="text/markdown"):
    return api_client.post(
        "/api/ingest/upload",
        files={"file": (name, body, mime)},
        headers=auth_headers_for(org),
    )


def _counts(api_client, org):
    clients = api_client.get("/api/monitor/clients", headers=auth_headers_for(org)).json()[
        "clients"
    ]
    return clients


def test_same_content_in_second_format_does_not_duplicate(api_client, clean_db, org_a, fake_ai):
    """The exact bug from the report: .md then .pdf of one fact-find."""
    first = _upload(api_client, org_a, "whitfield.md", FACT_FIND_TEXT.encode())
    assert first.status_code == 201, first.text
    assert first.json()["client_name"] == "Margaret & James Whitfield"

    # Same text, different bytes/extension (PDF parsing is faked by fake_ai,
    # so a .txt stands in for the second format; byte hashes differ).
    second = _upload(
        api_client, org_a, "whitfield-copy.txt", (FACT_FIND_TEXT + "  ").encode(), "text/plain"
    )
    assert second.status_code == 201, second.text
    body = second.json()
    assert body["note"] is not None and "Content matches" in body["note"]

    clients = _counts(api_client, org_a)
    assert [c["full_name"] for c in clients] == ["Margaret & James Whitfield"]
    assert clients[0]["open_alert_count"] == 2  # not 4


def test_same_client_new_content_merges_and_dedups_alerts(api_client, clean_db, org_a, monkeypatch, fake_ai):
    first = _upload(api_client, org_a, "factfind.md", FACT_FIND_TEXT.encode())
    assert first.status_code == 201

    # A later meeting note: same client, one overlapping alert + one new one.
    def meeting_note_extract(text: str):
        return {
            "client": {"full_name": "margaret & james  whitfield", "cash_savings": 96_000},
            "alerts": [
                {  # duplicate identity -> must be skipped
                    "trigger_date": "2025-07-10",
                    "type": "FOLLOW_UP",
                    "priority": "MEDIUM",
                    "title": "Bed & ISA Confirmation",
                    "description": "Chased again.",
                },
                {  # genuinely new -> must insert
                    "trigger_date": "2026-09-30",
                    "type": "DEADLINE",
                    "priority": "MEDIUM",
                    "title": "Mortgage fixed-rate ends",
                    "description": "Remortgage planning.",
                },
            ],
            "raw_text": text,
        }

    monkeypatch.setattr(
        "app.services.llm_extractor.extract_structured_from_text", meeting_note_extract
    )
    second = _upload(api_client, org_a, "meeting-note.md", b"Meeting with the Whitfields about mortgage and ISA follow-up items.")
    assert second.status_code == 201, second.text
    body = second.json()
    assert body["note"] is not None and "Merged into existing client" in body["note"]

    clients = _counts(api_client, org_a)
    assert len(clients) == 1
    assert clients[0]["open_alert_count"] == 3  # 2 original + 1 new, overlap deduplicated

    # Non-null field from the second document was merged onto the profile.
    detail = api_client.get(
        f"/api/monitor/clients/{clients[0]['id']}", headers=auth_headers_for(org_a)
    ).json()
    assert detail["cash_savings"] == 96_000
    assert detail["total_assets"] == 1_240_000  # untouched (None in doc 2)


def test_unknown_client_never_merges(api_client, clean_db, org_a, monkeypatch, fake_ai):
    def unknown_extract(text: str):
        return {"client": {"full_name": "Unknown Client"}, "alerts": [], "raw_text": text}

    monkeypatch.setattr(
        "app.services.llm_extractor.extract_structured_from_text", unknown_extract
    )
    for i in range(2):
        resp = _upload(api_client, org_a, f"mystery-{i}.md", f"Completely different unknown-content document number {i} with enough length.".encode())
        assert resp.status_code == 201
    clients = _counts(api_client, org_a)
    assert [c["full_name"] for c in clients] == ["Unknown Client", "Unknown Client"]


def test_merge_is_org_scoped(api_client, clean_db, org_a, org_b, fake_ai):
    """Org B's identically-named client never merges into org A's."""
    seed_client(clean_db, org_b.org_id, "Margaret & James Whitfield")
    resp = _upload(api_client, org_a, "whitfield.md", FACT_FIND_TEXT.encode())
    assert resp.status_code == 201
    assert resp.json()["note"] is None  # fresh client in org A, no merge
    a_clients = _counts(api_client, org_a)
    b_clients = _counts(api_client, org_b)
    assert len(a_clients) == 1 and len(b_clients) == 1
    assert a_clients[0]["id"] != b_clients[0]["id"]


def test_persist_extraction_retry_is_idempotent(clean_db, bind_org_a, fake_ai):
    """Re-running persistence for the same document (worker retry) is a no-op."""
    from app.routers.ingest import _persist_extraction, _store_document_row

    doc_id = str(uuid.uuid4())
    _store_document_row(
        org_id=bind_org_a.org_id,
        file_id=doc_id,
        display_filename="retry.md",
        content_hash="retry-hash",
        file_path=f"transcript:{doc_id}",
        file_size=100,
    )
    extracted = fake_ai(FACT_FIND_TEXT)
    first = _persist_extraction(extracted, "retry.md", ".md", doc_id)
    second = _persist_extraction(extracted, "retry.md", ".md", doc_id)
    assert first.error is None and second.error is None
    assert first.client_id == second.client_id

    from app.db import get_cursor

    with get_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n FROM alerts WHERE client_id = %s", (first.client_id,)
        )
        assert cur.fetchone()["n"] == 2  # not 4
