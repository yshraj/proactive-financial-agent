"""
In-memory background-job registry for asynchronous ingestion.

Tracks status/progress of work run via FastAPI BackgroundTasks (in-process, no
external worker or broker). Same in-memory convention as services/cache.py and
services/audit.py: not durable across restarts, acceptable for the current
single-instance deployment. Thread-safe; pure and fully unit-testable.
"""
from __future__ import annotations

import threading
from typing import Any, Optional

# Lifecycle states for a job.
PENDING = "PENDING"
PROCESSING = "PROCESSING"
DONE = "DONE"
ERROR = "ERROR"

_MAX_JOBS = 500
_jobs: "dict[str, dict[str, Any]]" = {}
_order: list[str] = []
_lock = threading.Lock()


def create(job_id: str, *, kind: str, filename: Optional[str] = None) -> dict[str, Any]:
    """Register a new job in the PENDING state and return it."""
    with _lock:
        job = {
            "id": job_id,
            "kind": kind,
            "filename": filename,
            "status": PENDING,
            "progress": 0,
            "message": "Queued",
            "document_id": None,
            "error": None,
        }
        _jobs[job_id] = job
        _order.append(job_id)
        _evict_if_needed()
        return dict(job)


def update(job_id: str, **fields: Any) -> Optional[dict[str, Any]]:
    """Patch a job's fields. Returns the updated job, or None if unknown."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        job.update(fields)
        return dict(job)


def get(job_id: str) -> Optional[dict[str, Any]]:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job is not None else None


def _evict_if_needed() -> None:
    """Drop oldest jobs beyond the cap. Caller holds the lock."""
    while len(_order) > _MAX_JOBS:
        oldest = _order.pop(0)
        _jobs.pop(oldest, None)


def clear() -> None:
    """Drop all jobs (used by the data-reset flow and tests)."""
    with _lock:
        _jobs.clear()
        _order.clear()
