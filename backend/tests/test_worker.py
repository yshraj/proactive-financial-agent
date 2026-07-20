"""Worker loop: job execution under tenant context, retries, idempotency."""
from __future__ import annotations

import uuid

from app.services import jobs
from app.worker import process_one


def test_worker_processes_upload_job_under_org_context(clean_db, org_a, monkeypatch, tmp_path):
    """A claimed upload job runs the ingestion handler with the job's org bound."""
    from app.routers.ingest import IngestOutcome
    from app.services import credits

    seen = {}

    def fake_ingestion(file_path, filename, ext, document_id, ingested_at, progress=None):
        from app.context import get_current_tenant

        seen["org_id"] = get_current_tenant().org_id
        seen["file_path"] = file_path
        if progress:
            progress(40, "AI extraction…")
        return IngestOutcome()  # success

    monkeypatch.setattr(
        "app.routers.ingest.run_dual_path_ingestion_from_storage", fake_ingestion
    )

    job_id = str(uuid.uuid4())
    reservation = credits.reserve(
        credits.CreditFeature.PDF_ANALYSIS, f"upload:{job_id}", ctx=org_a
    )
    jobs.create(
        job_id,
        kind="upload",
        filename="a.pdf",
        document_id=job_id,
        payload={
            "file_path": "uploads/x/a.pdf",
            "ext": ".pdf",
            "ingested_at": None,
            "credit_reservation_id": reservation.id,
        },
        ctx=org_a,
    )
    claimed = jobs.claim_next("worker-test")
    process_one(claimed)

    assert seen["org_id"] == org_a.org_id
    done = jobs.get(job_id, ctx=org_a)
    assert done["status"] == jobs.DONE
    assert done["progress"] == 100
    assert credits.get_summary(ctx=org_a)["used"] == 2


def test_worker_records_handler_error(clean_db, org_a, monkeypatch):
    from app.routers.ingest import IngestOutcome
    from app.services import credits

    def failing_ingestion(*args, **kwargs):
        return IngestOutcome(error="Extraction failed.")  # soft error path

    monkeypatch.setattr(
        "app.routers.ingest.run_dual_path_ingestion_from_storage", failing_ingestion
    )
    job_id = str(uuid.uuid4())
    reservation = credits.reserve(
        credits.CreditFeature.PDF_ANALYSIS, f"upload:{job_id}", ctx=org_a
    )
    jobs.create(job_id, kind="upload", document_id=job_id,
                payload={
                    "file_path": "x",
                    "ext": ".pdf",
                    "credit_reservation_id": reservation.id,
                }, ctx=org_a)
    process_one(jobs.claim_next("worker-test"))
    job = jobs.get(job_id, ctx=org_a)
    assert job["status"] == jobs.ERROR
    assert "Extraction failed" in (job["error"] or "")
    assert credits.get_summary(ctx=org_a)["used"] == 0
    assert credits.get_summary(ctx=org_a)["remaining"] == 200


def test_worker_requeues_crash_until_attempts_exhausted(clean_db, org_a, monkeypatch):
    calls = {"n": 0}

    def crashing_ingestion(*args, **kwargs):
        calls["n"] += 1
        raise RuntimeError("hard crash")

    monkeypatch.setattr(
        "app.routers.ingest.run_dual_path_ingestion_from_storage", crashing_ingestion
    )
    job_id = str(uuid.uuid4())
    jobs.create(job_id, kind="upload", document_id=job_id,
                payload={"file_path": "x", "ext": ".pdf"}, ctx=org_a)

    # Attempt 1 + 2: crash -> requeued as PENDING.
    for expected_status in (jobs.PENDING, jobs.PENDING, jobs.ERROR):
        claimed = jobs.claim_next("worker-test")
        assert claimed is not None
        process_one(claimed)
        assert jobs.get(job_id, ctx=org_a)["status"] == expected_status

    assert calls["n"] == 3
    assert jobs.claim_next("worker-test") is None  # nothing left to run


def test_unknown_job_kind_fails_cleanly(clean_db, org_a):
    job_id = str(uuid.uuid4())
    jobs.create(job_id, kind="mystery", ctx=org_a)
    process_one(jobs.claim_next("worker-test"))
    job = jobs.get(job_id, ctx=org_a)
    assert job["status"] == jobs.ERROR
    assert "No handler" in (job["error"] or "")
