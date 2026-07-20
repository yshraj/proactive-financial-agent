"""
Background worker: claims jobs from the Postgres queue and processes them.

Run as a dedicated process (Render background worker):

    cd backend && python -m app.worker

or embedded in the API process for single-service deployments and local dev
(INLINE_WORKER=true, the default — see app.main lifespan wiring in render.yaml,
which disables it once the dedicated worker service exists).

Guarantees:
- claims use FOR UPDATE SKIP LOCKED via the SECURITY DEFINER claim_next_job(),
  so concurrent workers never double-process;
- a job whose worker died mid-run is re-claimed after the stale-lock window
  and retried up to max_attempts (handlers are idempotent), then failed by the
  sweeper — restarts lose nothing;
- each job runs under its org's tenant context, so every query, cache write,
  and audit event it makes is tenant-scoped exactly like a request.
"""
from __future__ import annotations

import logging
import os
import signal
import socket
import threading
import time
from typing import Any, Optional

from app.context import set_current_tenant, set_request_id, system_context
from app.services import credits
from app.services import jobs

logger = logging.getLogger("jarvis.worker")

POLL_INTERVAL_SECONDS = float(os.environ.get("WORKER_POLL_SECONDS", "2"))
SWEEP_EVERY_SECONDS = 60.0


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
    except Exception as exc:  # noqa: BLE001 - job errors must not kill the loop
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
            jobs.update(job["id"], status=jobs.ERROR, progress=100,
                        message="Failed", error=str(exc)[:500])
        else:
            # Release for retry: back to PENDING, keeping the attempt count.
            jobs.update(job["id"], status=jobs.PENDING, message="Retry queued")
    finally:
        set_current_tenant(None)
        set_request_id(None)


def run_worker_loop(stop_event: Optional[threading.Event] = None) -> None:
    """Poll-claim-process loop. Returns when stop_event is set."""
    stop = stop_event or threading.Event()
    name = _worker_name()
    logger.info("Worker %s started (poll=%ss)", name, POLL_INTERVAL_SECONDS)
    last_sweep = 0.0
    while not stop.is_set():
        try:
            job = jobs.claim_next(name)
        except Exception:
            logger.exception("Job claim failed; backing off")
            stop.wait(min(POLL_INTERVAL_SECONDS * 5, 30))
            continue
        if job is not None:
            logger.info("Claimed job %s kind=%s org=%s attempt=%s",
                        job["id"], job["kind"], job["org_id"], job.get("attempts"))
            process_one(job)
            continue  # drain the queue before sleeping
        now = time.monotonic()
        if now - last_sweep > SWEEP_EVERY_SECONDS:
            last_sweep = now
            try:
                failed = jobs.sweep_exhausted()
                if failed:
                    logger.warning("Swept %d exhausted job(s) to ERROR", failed)
            except Exception:
                logger.exception("Job sweep failed")
        stop.wait(POLL_INTERVAL_SECONDS)
    logger.info("Worker %s stopped", name)


def start_inline_worker() -> threading.Event:
    """Run the worker loop in a daemon thread inside the API process."""
    stop = threading.Event()
    thread = threading.Thread(target=run_worker_loop, args=(stop,), daemon=True,
                              name="inline-worker")
    thread.start()
    return stop


def main() -> None:
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")

    from app.logging_config import configure_logging
    from app.observability import init_sentry

    configure_logging()
    init_sentry()

    stop = threading.Event()

    def _signal_handler(signum, frame):  # noqa: ARG001
        logger.info("Signal %s received; shutting down after current job", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    run_worker_loop(stop)


if __name__ == "__main__":
    main()
