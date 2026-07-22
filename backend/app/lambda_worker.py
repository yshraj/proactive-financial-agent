"""
AWS Lambda entry point for the queue worker.

Invoked two ways (both fire-and-forget, InvocationType=Event):

- by the API right after a job is enqueued (app/services/worker_trigger.py),
- by an EventBridge Scheduler rule every few minutes as a safety net for
  missed triggers, stale-lock retries, and exhausted-job sweeps.

The handler drains the queue until it is empty or the invocation's time
budget runs low; in the latter case it re-invokes itself so the remainder of
the backlog gets a fresh 15-minute budget. Overlapping invocations are safe
(claims are FOR UPDATE SKIP LOCKED) but avoided via reserved concurrency = 1
on the function — throttled events are simply retried by Lambda's async
queue.

Packaging: the ``worker`` target in backend/Dockerfile runs this module via
``awslambdaric``; infrastructure lives in deploy/aws/template.yaml.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from app.logging_config import configure_logging
from app.observability import init_sentry

# Cold-start initialisation: once per execution environment.
configure_logging()
init_sentry()

logger = logging.getLogger("jarvis.worker.lambda")


def handler(event: Optional[dict[str, Any]], context: Any) -> dict[str, Any]:
    """Drain the job queue within this invocation's remaining time budget."""
    from app.services.worker_trigger import invoke_worker
    from app.worker import drain_queue

    reason = (event or {}).get("reason") or "schedule"
    stats = drain_queue(context.get_remaining_time_in_millis)

    reinvoked = False
    if stats.backlog:
        # Ran out of budget with work still queued: hand the remainder to a
        # fresh invocation instead of dying mid-job.
        reinvoked = invoke_worker(
            "backlog-continuation",
            function_name=os.environ.get("AWS_LAMBDA_FUNCTION_NAME"),
        )

    result = {
        "reason": reason,
        "processed": stats.processed,
        "swept": stats.swept,
        "backlog": stats.backlog,
        "reinvoked": reinvoked,
    }
    logger.info(
        "Worker invocation done: reason=%s processed=%d swept=%d backlog=%s reinvoked=%s",
        reason, stats.processed, stats.swept, stats.backlog, reinvoked,
        extra={"event": "worker_invocation", **result},
    )
    return result
