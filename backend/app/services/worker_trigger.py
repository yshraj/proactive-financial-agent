"""
Fire-and-forget trigger for the queue worker — the event-driven replacement
for the old 2-second polling loop.

Two modes, chosen by whether ``WORKER_FUNCTION_NAME`` is set:

- **AWS (Lambda):** asynchronously invoke the worker Lambda
  (InvocationType=Event) right after a job is enqueued. Failures are logged
  and swallowed — the enqueue already succeeded, and the scheduled safety-net
  drain (EventBridge, every 5 minutes) picks up any job whose trigger was
  lost. We deliberately never fall back to in-process draining here: a Lambda
  execution environment freezes as soon as the response is sent, so
  background work would silently stall.

- **Local / docker-compose (no WORKER_FUNCTION_NAME):** run one queue drain
  as a FastAPI background task after the response is sent. Still
  event-driven — no polling loop, no daemon thread. Concurrent drains are
  safe (claims are FOR UPDATE SKIP LOCKED).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from fastapi import BackgroundTasks

from app.context import get_request_id

logger = logging.getLogger("jarvis.worker_trigger")

_lambda_client: Any = None


def worker_function_name() -> str:
    """Name/ARN of the worker Lambda, or '' when running without one."""
    return (os.environ.get("WORKER_FUNCTION_NAME") or "").strip()


def _client() -> Any:
    """boto3 Lambda client, created once per process / execution environment."""
    global _lambda_client
    if _lambda_client is None:
        import boto3  # deferred: only needed when a worker Lambda is configured

        _lambda_client = boto3.client("lambda")
    return _lambda_client


def invoke_worker(reason: str, *, function_name: Optional[str] = None) -> bool:
    """Asynchronously invoke the worker Lambda. Never raises.

    Returns True when Lambda accepted the event (HTTP 202), False otherwise.
    """
    name = function_name or worker_function_name()
    if not name:
        return False
    payload = {"reason": reason, "request_id": get_request_id() or ""}
    try:
        response = _client().invoke(
            FunctionName=name,
            InvocationType="Event",
            Payload=json.dumps(payload).encode("utf-8"),
        )
        accepted = int(response.get("StatusCode") or 0) == 202
        if not accepted:
            logger.warning(
                "Worker invoke not accepted (status=%s); scheduled drain will cover",
                response.get("StatusCode"),
                extra={"event": "worker_invoke_rejected", "reason": reason},
            )
        return accepted
    except Exception:
        logger.exception(
            "Worker Lambda invoke failed; scheduled drain will cover",
            extra={"event": "worker_invoke_failed", "reason": reason},
        )
        return False


def _drain_in_process() -> None:
    """One unbounded drain pass (local/compose fallback, runs post-response)."""
    from app.worker import drain_queue

    drain_queue(lambda: float("inf"))


def trigger_drain(background_tasks: BackgroundTasks, *, reason: str) -> None:
    """Kick the worker after enqueueing a job (see module docstring)."""
    if worker_function_name():
        invoke_worker(reason)
        return
    background_tasks.add_task(_drain_in_process)
