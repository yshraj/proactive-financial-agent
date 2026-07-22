"""Event-driven worker trigger + drain budget semantics (no AWS, no DB)."""
from __future__ import annotations

import json

import pytest
from fastapi import BackgroundTasks

from app import worker
from app.services import worker_trigger
from app.worker import DrainStats


@pytest.fixture(autouse=True)
def _reset_lambda_client():
    worker_trigger._lambda_client = None
    yield
    worker_trigger._lambda_client = None


class FakeLambdaClient:
    def __init__(self, status: int = 202, exc: Exception | None = None):
        self.status = status
        self.exc = exc
        self.calls: list[dict] = []

    def invoke(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        return {"StatusCode": self.status}


# ---------------------------------------------------------------------------
# trigger_drain / invoke_worker
# ---------------------------------------------------------------------------


def test_trigger_invokes_worker_lambda_when_configured(monkeypatch):
    fake = FakeLambdaClient()
    monkeypatch.setenv("WORKER_FUNCTION_NAME", "kritifin-backend-worker")
    worker_trigger._lambda_client = fake

    tasks = BackgroundTasks()
    worker_trigger.trigger_drain(tasks, reason="upload-enqueued")

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["FunctionName"] == "kritifin-backend-worker"
    assert call["InvocationType"] == "Event"
    assert json.loads(call["Payload"])["reason"] == "upload-enqueued"
    # No local fallback when the Lambda path handled it.
    assert tasks.tasks == []


def test_trigger_swallows_invoke_failure(monkeypatch):
    """A lost trigger must never fail the upload; the schedule covers it."""
    fake = FakeLambdaClient(exc=RuntimeError("aws is down"))
    monkeypatch.setenv("WORKER_FUNCTION_NAME", "kritifin-backend-worker")
    worker_trigger._lambda_client = fake

    tasks = BackgroundTasks()
    worker_trigger.trigger_drain(tasks, reason="upload-enqueued")  # no raise

    assert len(fake.calls) == 1
    # Deliberately no in-process fallback on Lambda (env freezes post-response).
    assert tasks.tasks == []


def test_trigger_falls_back_to_background_task_locally(monkeypatch):
    monkeypatch.delenv("WORKER_FUNCTION_NAME", raising=False)
    drained = []
    monkeypatch.setattr(worker, "drain_queue", lambda remaining_ms: drained.append(remaining_ms))

    tasks = BackgroundTasks()
    worker_trigger.trigger_drain(tasks, reason="upload-enqueued")

    assert len(tasks.tasks) == 1
    tasks.tasks[0].func()  # run the scheduled drain
    assert len(drained) == 1
    assert drained[0]() == float("inf")  # local drains are unbounded


def test_invoke_worker_without_name_is_noop(monkeypatch):
    monkeypatch.delenv("WORKER_FUNCTION_NAME", raising=False)
    assert worker_trigger.invoke_worker("whatever") is False


def test_invoke_worker_reports_unexpected_status(monkeypatch):
    fake = FakeLambdaClient(status=500)
    worker_trigger._lambda_client = fake
    assert worker_trigger.invoke_worker("r", function_name="w") is False


# ---------------------------------------------------------------------------
# drain_queue budget/backlog semantics
# ---------------------------------------------------------------------------


def _fake_job(job_id: str) -> dict:
    return {"id": job_id, "kind": "upload", "org_id": "org-1", "attempts": 1}


def test_drain_processes_until_queue_empty(monkeypatch):
    monkeypatch.setattr(worker.jobs, "sweep_exhausted", lambda: 0)
    queue = [_fake_job("a"), _fake_job("b")]
    monkeypatch.setattr(worker.jobs, "claim_next", lambda name: queue.pop(0) if queue else None)
    processed = []
    monkeypatch.setattr(worker, "process_one", lambda job: processed.append(job["id"]))

    stats = worker.drain_queue(lambda: 10_000_000)

    assert processed == ["a", "b"]
    assert stats == DrainStats(processed=2, swept=0, backlog=False)


def test_drain_stops_on_low_budget_and_reports_backlog(monkeypatch):
    monkeypatch.setattr(worker.jobs, "sweep_exhausted", lambda: 1)
    monkeypatch.setattr(worker.jobs, "claim_next", lambda name: _fake_job("x"))
    monkeypatch.setattr(worker.jobs, "has_runnable", lambda: True)
    monkeypatch.setattr(worker, "process_one", lambda job: None)
    budgets = iter([1_000_000, 200_000])  # one job fits, then under the floor

    stats = worker.drain_queue(lambda: next(budgets))

    assert stats.processed == 1
    assert stats.swept == 1
    assert stats.backlog is True


def test_drain_reports_no_backlog_when_queue_emptied_at_budget_floor(monkeypatch):
    """Budget exhaustion with an empty queue must not trigger a re-invoke."""
    monkeypatch.setattr(worker.jobs, "sweep_exhausted", lambda: 0)
    monkeypatch.setattr(worker.jobs, "claim_next", lambda name: _fake_job("x"))
    monkeypatch.setattr(worker.jobs, "has_runnable", lambda: False)
    monkeypatch.setattr(worker, "process_one", lambda job: None)
    budgets = iter([1_000_000, 200_000])  # last job consumed the budget

    stats = worker.drain_queue(lambda: next(budgets))

    assert stats.processed == 1
    assert stats.backlog is False


def test_drain_assumes_backlog_when_probe_fails(monkeypatch):
    """A failed existence probe must fail safe (one cheap extra invocation)."""
    monkeypatch.setattr(worker.jobs, "sweep_exhausted", lambda: 0)
    monkeypatch.setattr(worker.jobs, "claim_next", lambda name: _fake_job("x"))
    monkeypatch.setattr(worker, "process_one", lambda job: None)

    def probe_boom():
        raise RuntimeError("db blip")

    monkeypatch.setattr(worker.jobs, "has_runnable", probe_boom)
    budgets = iter([1_000_000, 200_000])

    stats = worker.drain_queue(lambda: next(budgets))

    assert stats.backlog is True


def test_drain_continues_when_process_one_escapes(monkeypatch):
    """Even a failure while *recording* a job failure must not stop the drain."""
    monkeypatch.setattr(worker.jobs, "sweep_exhausted", lambda: 0)
    queue = [_fake_job("a"), _fake_job("b")]
    monkeypatch.setattr(worker.jobs, "claim_next", lambda name: queue.pop(0) if queue else None)
    seen = []

    def exploding_process(job):
        seen.append(job["id"])
        if job["id"] == "a":
            raise RuntimeError("update failed mid-crash-handling")

    monkeypatch.setattr(worker, "process_one", exploding_process)

    stats = worker.drain_queue(lambda: 10_000_000)

    assert seen == ["a", "b"]  # b still processed after a escaped
    assert stats.processed == 2
    assert stats.backlog is False


def test_drain_survives_sweep_failure(monkeypatch):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(worker.jobs, "sweep_exhausted", boom)
    monkeypatch.setattr(worker.jobs, "claim_next", lambda name: None)

    stats = worker.drain_queue(lambda: 10_000_000)

    assert stats == DrainStats(processed=0, swept=0, backlog=False)


def test_drain_claim_failure_ends_without_backlog(monkeypatch):
    """DB trouble must not trigger a self-re-invoke loop; the schedule retries."""
    monkeypatch.setattr(worker.jobs, "sweep_exhausted", lambda: 0)

    def boom(name):
        raise RuntimeError("db down")

    monkeypatch.setattr(worker.jobs, "claim_next", boom)

    stats = worker.drain_queue(lambda: 10_000_000)

    assert stats.backlog is False
    assert stats.processed == 0


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------


class _FakeContext:
    @staticmethod
    def get_remaining_time_in_millis() -> int:
        return 900_000


def test_lambda_handler_drains_and_reports(monkeypatch):
    from app import lambda_worker

    monkeypatch.setattr("app.worker.drain_queue", lambda fn: DrainStats(processed=2))

    result = lambda_worker.handler({"reason": "upload-enqueued"}, _FakeContext())

    assert result == {
        "reason": "upload-enqueued",
        "processed": 2,
        "swept": 0,
        "backlog": False,
        "reinvoked": False,
    }


def test_lambda_handler_reinvokes_self_on_backlog(monkeypatch):
    from app import lambda_worker

    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "kritifin-backend-worker")
    monkeypatch.setattr(
        "app.worker.drain_queue",
        lambda fn: DrainStats(processed=3, swept=1, backlog=True),
    )
    calls = []

    def fake_invoke(reason, *, function_name=None):
        calls.append((reason, function_name))
        return True

    monkeypatch.setattr("app.services.worker_trigger.invoke_worker", fake_invoke)

    result = lambda_worker.handler(None, _FakeContext())

    assert result["reason"] == "schedule"  # default when no payload
    assert result["backlog"] is True
    assert result["reinvoked"] is True
    assert calls == [("backlog-continuation", "kritifin-backend-worker")]
