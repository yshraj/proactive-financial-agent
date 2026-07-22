"""Durable Postgres job queue: enqueue, claim, retry, restart survival."""
from __future__ import annotations

import uuid

from app.services import jobs


def _new_id() -> str:
    return str(uuid.uuid4())


def test_create_starts_pending(bind_org_a):
    job = jobs.create(_new_id(), kind="upload", filename="a.pdf")
    assert job["status"] == jobs.PENDING
    assert job["progress"] == 0
    assert job["filename"] == "a.pdf"


def test_update_patches_fields(bind_org_a):
    job_id = _new_id()
    jobs.create(job_id, kind="upload")
    doc_id = _new_id()
    updated = jobs.update(job_id, status=jobs.DONE, progress=100, document_id=doc_id)
    assert updated["status"] == jobs.DONE
    assert updated["progress"] == 100
    assert updated["document_id"] == doc_id


def test_update_unknown_returns_none(bind_org_a):
    assert jobs.update(_new_id(), status=jobs.DONE) is None


def test_get_unknown_returns_none(bind_org_a):
    assert jobs.get(_new_id()) is None


def test_clear_empties_registry(bind_org_a):
    job_id = _new_id()
    jobs.create(job_id, kind="upload")
    jobs.clear()
    assert jobs.get(job_id) is None


def test_jobs_survive_reconnect(bind_org_a, clean_db):
    from app.db import close_pool

    job_id = _new_id()
    jobs.create(job_id, kind="upload", filename="persists.pdf")
    close_pool()  # simulate process restart
    job = jobs.get(job_id)
    assert job is not None
    assert job["filename"] == "persists.pdf"


def test_jobs_are_org_scoped(clean_db, org_a, org_b):
    job_id = _new_id()
    jobs.create(job_id, kind="upload", ctx=org_a)
    assert jobs.get(job_id, ctx=org_a) is not None
    assert jobs.get(job_id, ctx=org_b) is None  # invisible across the boundary


def test_claim_next_processes_fifo_and_increments_attempts(bind_org_a, clean_db):
    first, second = _new_id(), _new_id()
    jobs.create(first, kind="upload")
    jobs.create(second, kind="upload")

    claimed = jobs.claim_next("worker-test")
    assert claimed is not None
    assert claimed["id"] == first
    assert claimed["status"] == jobs.PROCESSING
    assert claimed["attempts"] == 1

    claimed2 = jobs.claim_next("worker-test")
    assert claimed2["id"] == second

    # Nothing left to claim (both PROCESSING with fresh locks).
    assert jobs.claim_next("worker-test") is None


def test_stale_processing_job_is_reclaimed(bind_org_a, clean_db, org_a):
    """A worker that died mid-job leaves a stale lock; it must be re-claimable."""
    import psycopg2

    job_id = _new_id()
    jobs.create(job_id, kind="upload")
    claimed = jobs.claim_next("worker-1")
    assert claimed["id"] == job_id

    # Age the lock beyond the stale window (admin connection).
    conn = psycopg2.connect(clean_db["admin"])
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET locked_at = NOW() - INTERVAL '1 hour' WHERE id = %s", (job_id,)
        )
    conn.close()

    reclaimed = jobs.claim_next("worker-2")
    assert reclaimed is not None
    assert reclaimed["id"] == job_id
    assert reclaimed["attempts"] == 2


def test_has_runnable_tracks_claimable_work(bind_org_a, clean_db):
    """The drain's backlog probe: PENDING or stale-retryable PROCESSING only."""
    import psycopg2

    assert jobs.has_runnable() is False  # empty queue

    job_id = _new_id()
    jobs.create(job_id, kind="upload")
    assert jobs.has_runnable() is True  # PENDING

    jobs.claim_next("worker-1")
    assert jobs.has_runnable() is False  # PROCESSING with a fresh lock

    # Age the lock beyond the stale window -> claimable again.
    conn = psycopg2.connect(clean_db["admin"])
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET locked_at = NOW() - INTERVAL '1 hour' WHERE id = %s", (job_id,)
        )
    conn.close()
    assert jobs.has_runnable() is True

    jobs.claim_next("worker-2")
    jobs.update(job_id, status=jobs.DONE, progress=100)
    assert jobs.has_runnable() is False  # finished work is not runnable


def test_exhausted_stale_jobs_are_swept_to_error(bind_org_a, clean_db):
    import psycopg2

    job_id = _new_id()
    jobs.create(job_id, kind="upload")
    jobs.claim_next("worker-1")

    conn = psycopg2.connect(clean_db["admin"])
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET locked_at = NOW() - INTERVAL '1 hour', attempts = max_attempts"
            " WHERE id = %s",
            (job_id,),
        )
    conn.close()

    swept = jobs.sweep_exhausted()
    assert swept == 1
    assert jobs.get(job_id)["status"] == jobs.ERROR
