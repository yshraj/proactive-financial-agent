"""
Background worker: claims jobs from the Postgres queue and processes them.

Event-driven (no polling loop): the API triggers a queue drain right after
enqueueing a job —

- on AWS Lambda by asynchronously invoking the worker function
  (``app/lambda_worker.py``), and
- locally / in docker-compose via a FastAPI background task

both via ``app.services.worker_trigger.trigger_drain``. An EventBridge
schedule invokes the worker Lambda every few minutes as a safety net for
missed triggers, retries, and stale-job sweeps.

Guarantees:
- claims use FOR UPDATE SKIP LOCKED via the SECURITY DEFINER claim_next_job(),
  so concurrent drains never double-process;
- a job whose worker died mid-run (crash, restart, Lambda timeout) is
  re-claimed after the stale-lock window and retried up to max_attempts
  (handlers are idempotent), then failed by the sweeper — nothing is lost;
- each job runs under its org's tenant context, so every query, cache write,
  and audit event it makes is tenant-scoped exactly like a request.
"""
from __future__ import annotations

import logging
import os
import socket
from dataclasses import dataclass
from typing import Any, Callable

from app.context import set_current_tenant, set_request_id, system_context
from app.services import credits
from app.services import jobs

logger = logging.getLogger("jarvis.worker")

# Don't start another job unless at least this much execution budget remains.
# Sized to a worst-case single-document ingestion; a job that still overruns
# is recovered by the stale-lock reclaim in claim_next_job().
MIN_REMAINING_TO_START_MS = 300_000


def _worker_name() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _process_upload_job(job: dict[str, Any]) -> None:
    """Run dual-path ingestion for a stored document and record progress."""
    from app.routers.ingest import run_dual_path_ingestion_from_storage

    payload = job.get("payload") or {}
    file_path = payload.get("file_path") or ""
    ext = payload.get("ext") or ".pdf"
    ingested_at = payload.get("ingested_at")
    document_id = job.get("document_id") or job["id"]

    def report(pct: int, message: str) -> None:
        # Stage updates power the UI progress bar (poll GET /jobs/{id}).
        jobs.update(job["id"], status=jobs.PROCESSING, progress=pct, message=message)

    outcome = run_dual_path_ingestion_from_storage(
        file_path, job.get("filename") or "document", ext, document_id, ingested_at,
        progress=report,
    )
    reservation_id = payload.get("credit_reservation_id")
    if outcome.error or not outcome.ai_generated:
        if reservation_id:
            credits.release(str(reservation_id))
        if outcome.error:
            jobs.update(job["id"], status=jobs.ERROR, progress=100,
                        message="Completed with issues", error=outcome.error,
                        document_id=document_id)
        else:
            jobs.update(job["id"], status=jobs.DONE, progress=100,
                        message=outcome.note or "Done", document_id=document_id)
    else:
        if reservation_id:
            credits.commit(str(reservation_id))
        jobs.update(job["id"], status=jobs.DONE, progress=100,
                    message=outcome.note or "Done", document_id=document_id)


_HANDLERS = {
    "upload": _process_upload_job,
}


def process_one(job: dict[str, Any]) -> None:
    """Execute a claimed job under its org's tenant context."""
    ctx = system_context(job["org_id"], request_id=f"job-{job['id'][:8]}")
    set_current_tenant(ctx)
    set_request_id(ctx.request_id)
    try:
        handler = _HANDLERS.get(job["kind"])
        if handler is None:
            reservation_id = (job.get("payload") or {}).get("credit_reservation_id")
            if reservation_id:
                credits.release(str(reservation_id))
            jobs.update(job["id"], status=jobs.ERROR, progress=100, message="Failed",
                        error=f"No handler for job kind {job['kind']!r}")
            return
        handler(job)
    except Exception as exc:  # noqa: BLE001 - job errors must not kill the drain
        logger.exception("Job %s failed: %s", job["id"], exc)
        attempts, max_attempts = int(job.get("attempts") or 1), 3
        try:
            max_attempts = int(job.get("max_attempts") or 3)
        except (TypeError, ValueError):
            pass
        if attempts >= max_attempts:
            reservation_id = (job.get("payload") or {}).get("credit_reservation_id")
            if reservation_id:
                credits.release(str(reservation_id))
            # job.error is user-visible via GET /jobs/{id}: fixed copy only,
            # the real exception is already in the logs above.
            from app.services.safety import public_error_message

            jobs.update(job["id"], status=jobs.ERROR, progress=100,
                        message="Failed", error=public_error_message("job_failed"))
        else:
            # Release for retry: back to PENDING, keeping the attempt count.
            jobs.update(job["id"], status=jobs.PENDING, message="Retry queued")
    finally:
        set_current_tenant(None)
        set_request_id(None)


@dataclass
class DrainStats:
    """Outcome of one drain pass."""

    processed: int = 0
    swept: int = 0
    # True when the drain stopped on its time budget with work (probably)
    # still queued — the caller should schedule a follow-up drain.
    backlog: bool = False


def drain_queue(
    remaining_ms: Callable[[], float],
    *,
    min_remaining_to_start_ms: int = MIN_REMAINING_TO_START_MS,
) -> DrainStats:
    """Sweep exhausted jobs, then claim-and-process until the queue is empty
    or the execution budget runs low.

    ``remaining_ms`` returns the execution budget left (on Lambda:
    ``context.get_remaining_time_in_millis``; locally: unbounded). Safe to run
    concurrently — claims are FOR UPDATE SKIP LOCKED.
    """
    stats = DrainStats()
    name = _worker_name()
    try:
        stats.swept = jobs.sweep_exhausted()
        if stats.swept:
            logger.warning("Swept %d exhausted job(s) to ERROR", stats.swept)
    except Exception:
        logger.exception("Job sweep failed; continuing with drain")
    while True:
        if remaining_ms() < min_remaining_to_start_ms:
            # Out of budget: hand remaining work to a fresh invocation rather
            # than risk dying inside a job — but check there IS work first so
            # an empty queue doesn't trigger a pointless re-invoke.
            try:
                stats.backlog = jobs.has_runnable()
            except Exception:
                # Probe failed (DB blip): assume backlog. The follow-up drain
                # is cheap and cannot loop — its claim failure ends without
                # backlog, leaving recovery to the scheduled safety net.
                logger.exception("Backlog probe failed; assuming backlog")
                stats.backlog = True
            break
        try:
            job = jobs.claim_next(name)
        except Exception:
            # DB trouble: don't signal backlog (avoids a re-invoke loop);
            # the scheduled safety-net drain retries in a few minutes.
            logger.exception("Job claim failed; ending drain")
            break
        if job is None:
            break
        logger.info("Claimed job %s kind=%s org=%s attempt=%s",
                    job["id"], job["kind"], job["org_id"], job.get("attempts"))
        try:
            process_one(job)
        except Exception:
            # process_one handles job errors itself; reaching here means even
            # recording the failure failed (e.g. DB blip mid-update). The job
            # stays PROCESSING and is re-claimed after the stale-lock window.
            # Keep draining — the next claim will surface a real DB outage.
            logger.exception("Job %s escaped its handler; continuing drain", job["id"])
        stats.processed += 1
    logger.info(
        "Drain finished: processed=%d swept=%d backlog=%s",
        stats.processed, stats.swept, stats.backlog,
        extra={
            "event": "worker_drain",
            "processed": stats.processed,
            "swept": stats.swept,
            "backlog": stats.backlog,
        },
    )
    return stats
