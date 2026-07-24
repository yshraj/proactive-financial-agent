"""
Agent runs API: create a durable multi-agent run and poll its progress.

POST /api/agent/runs enqueues the run on the existing Postgres job queue
(worker Lambda drains it — the 180s API budget never runs a graph) and
returns a run id. GET /api/agent/runs/{id} returns status + the real
per-node step timeline (plan, tool calls, synthesis, compliance review)
that the frontend renders instead of the simulated thinking card.

Credits follow the ingest upload-async pattern: reserve here, commit in the
worker on success, release on failure/exhaustion.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.context import TenantContext
from app.db import get_cursor
from app.deps import current_tenant
from app.security import limiter
from app.services import agent_runs, audit, conversations, credits, jobs, worker_trigger
from app.services.safety import sanitize_user_query

router = APIRouter()

_KIND_FEATURES = {
    "copilot": credits.CreditFeature.CHAT,
    "brief": credits.CreditFeature.REPORT,
}


class AgentRunRequest(BaseModel):
    kind: str = Field(..., pattern="^(copilot|brief)$")
    query: Optional[str] = Field(default=None, max_length=2000)
    client_id: Optional[str] = Field(default=None, max_length=64)
    conversation_id: Optional[str] = Field(default=None, max_length=64)


class AgentRunCreateResponse(BaseModel):
    run_id: str
    status: str
    conversation_id: Optional[str] = None


class AgentStepOut(BaseModel):
    seq: int
    node: str
    label: str
    status: str
    detail: Optional[dict] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class AgentRunStatusResponse(BaseModel):
    id: str
    kind: str
    status: str
    error: Optional[str] = None
    output: Optional[dict] = None
    steps: list[AgentStepOut] = []
    conversation_id: Optional[str] = None
    client_id: Optional[str] = None
    created_at: Optional[str] = None
    finished_at: Optional[str] = None


def _require_client(ctx: TenantContext, client_id: str) -> None:
    with get_cursor() as cur:
        cur.execute(
            "SELECT id FROM clients WHERE id = %s AND org_id = %s", (client_id, ctx.org_id)
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Client not found")


@router.post("/runs", response_model=AgentRunCreateResponse, status_code=202)
@limiter.limit("20/minute")
def create_run(
    request: Request,
    response: Response,  # slowapi injects X-RateLimit headers (headers_enabled)
    body: AgentRunRequest,
    background_tasks: BackgroundTasks,
    ctx: TenantContext = Depends(current_tenant),
):
    """Create an agent run, reserve credits, enqueue the job, kick the worker."""
    kind = body.kind
    query = sanitize_user_query(body.query or "")
    client_id = (body.client_id or "").strip() or None

    if kind == "copilot" and not query:
        raise HTTPException(status_code=400, detail="query is required for copilot runs")
    if kind == "brief" and not client_id:
        raise HTTPException(status_code=400, detail="client_id is required for brief runs")
    if client_id:
        _require_client(ctx, client_id)

    conversation_id: Optional[str] = None
    if kind == "copilot":
        conversation_id = (body.conversation_id or "").strip() or None
        if conversation_id and not conversations.exists(conversation_id):
            conversation_id = None
        if conversation_id is None:
            conversation_id = conversations.create(client_id=client_id)

    feature = _KIND_FEATURES[kind]
    reservation = credits.reserve(
        feature,
        credits.request_idempotency_key(request, feature),
        ctx=ctx,
    )
    try:
        run = agent_runs.create(
            kind=kind,
            input_payload={"query": query},
            conversation_id=conversation_id,
            client_id=client_id,
            ctx=ctx,
        )
        jobs.create(
            str(uuid.uuid4()),
            kind="agent_run",
            payload={
                "run_id": run["id"],
                "credit_reservation_id": reservation.id,
            },
        )
    except BaseException:
        credits.release(reservation.id, ctx=ctx)
        raise

    audit.record_event(
        action="ai.agent_run.requested",
        resource_type="agent_run",
        resource_id=run["id"],
        client_id=client_id,
        metadata={"kind": kind, "conversation_id": conversation_id},
    )
    worker_trigger.trigger_drain(background_tasks, reason="agent-run-enqueued")
    return AgentRunCreateResponse(
        run_id=run["id"], status=run["status"], conversation_id=conversation_id
    )


@router.get("/runs/{run_id}", response_model=AgentRunStatusResponse)
@limiter.limit("240/minute")
def get_run(
    request: Request,
    response: Response,  # slowapi injects X-RateLimit headers (headers_enabled)
    run_id: str,
    ctx: TenantContext = Depends(current_tenant),
):
    """Poll a run: status, real step timeline, and the output when done."""
    run = agent_runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    steps = agent_runs.get_steps(run_id)
    output: Optional[dict[str, Any]] = run.get("output") if run["status"] == agent_runs.DONE else None
    return AgentRunStatusResponse(
        id=run["id"],
        kind=run["kind"],
        status=run["status"],
        error=run.get("error"),
        output=output,
        steps=[AgentStepOut(**s) for s in steps],
        conversation_id=run.get("conversation_id"),
        client_id=run.get("client_id"),
        created_at=run.get("created_at"),
        finished_at=run.get("finished_at"),
    )
