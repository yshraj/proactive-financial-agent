"""
RLS-scoped tool layer for the agent runtime.

Every tool takes the TenantContext explicitly (agent runs execute in worker
threads where contextvars from the request do not apply) and only reads
through the same org-scoped paths the routers use — Qdrant searches carry the
mandatory ``org_id`` filter, SQL runs under the tenant GUCs, so an agent
physically cannot cross a tenant boundary.

Tools are deliberately read-only in this iteration: the copilot/brief graph
gathers and reasons; actions that mutate data stay behind the existing
credit-gated endpoints until the human-approval gate ships.

The OpenAI-style schemas in TOOL_SCHEMAS are what the planner model sees;
``execute_tool`` is the only dispatch path and rejects anything outside the
whitelist.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from app.context import TenantContext

logger = logging.getLogger("jarvis.agent_tools")

# Bounds: tools must stay cheap and prompt-sized.
_MAX_ALERT_ROWS = 20
_CONTEXT_CHAR_CAP = 6000


def search_documents(
    ctx: TenantContext, *, query: str, client_id: Optional[str] = None
) -> dict[str, Any]:
    """Semantic search over ingested documents (org-filtered Qdrant)."""
    from app.services.rag_context import retrieve_for_chat

    context, sources = retrieve_for_chat(
        (query or "")[:500], org_id=ctx.org_id, client_id=client_id or None
    )
    return {
        "context": context[:_CONTEXT_CHAR_CAP],
        "sources": sources,
        "summary": f"{len(sources)} document excerpt(s) found",
    }


def get_structured_context(
    ctx: TenantContext, *, client_id: Optional[str] = None
) -> dict[str, Any]:
    """Compact structured snapshot: clients, reviews, alerts, follow-ups."""
    # Lazy import from the router module: the builder lives there today
    # because request tests monkeypatch it; the agent reuses it unchanged.
    from app.routers.chat import _get_structured_context as build

    context = build(ctx, client_id or None)
    return {"context": context[:_CONTEXT_CHAR_CAP], "summary": "structured records loaded"}


def get_book_analytics(ctx: TenantContext) -> dict[str, Any]:
    """Deterministic book-level metrics (clients, AUM, avg risk, overdue)."""
    from app.db import get_cursor
    from app.services.analytics import compute_book_analytics

    with get_cursor(ctx=ctx) as cur:
        cur.execute(
            """
            SELECT total_assets, risk_score, last_review_date
            FROM clients WHERE org_id = %s
            """,
            (ctx.org_id,),
        )
        rows = cur.fetchall()
    metrics = compute_book_analytics([dict(r) for r in rows], datetime.now().date())
    return {"metrics": metrics, "summary": f"analytics over {metrics['clients_total']} client(s)"}


def get_client_scores(ctx: TenantContext, *, client_id: str) -> dict[str, Any]:
    """Deterministic client-intelligence scores (no LLM arithmetic)."""
    from app.db import get_cursor
    from app.services.analytics import REVIEW_OVERDUE_DAYS
    from app.services.scores import at_risk_score, next_best_actions, planning_completeness

    today = datetime.now().date()
    with get_cursor(ctx=ctx) as cur:
        cur.execute(
            """
            SELECT full_name, total_assets, cash_savings, risk_score,
                   retirement_target_age, last_review_date
            FROM clients WHERE id = %s AND org_id = %s
            """,
            (client_id, ctx.org_id),
        )
        row = cur.fetchone()
        if not row:
            return {"error": "Client not found", "summary": "client not found"}
        cur.execute(
            """
            SELECT title, type, priority, trigger_date
            FROM alerts
            WHERE client_id = %s AND org_id = %s AND status = 'PENDING'
            ORDER BY trigger_date
            LIMIT %s
            """,
            (client_id, ctx.org_id, _MAX_ALERT_ROWS),
        )
        alerts = cur.fetchall()

    last_review = row.get("last_review_date")
    overdue_follow_ups = [
        a for a in alerts
        if a.get("type") == "FOLLOW_UP" and a.get("trigger_date") and a["trigger_date"] < today
    ]
    high_priority = sum(1 for a in alerts if a.get("priority") == "HIGH")
    completeness = planning_completeness(dict(row))
    risk = at_risk_score(
        last_review=last_review,
        today=today,
        overdue_follow_ups=len(overdue_follow_ups),
        high_priority_alerts=high_priority,
    )
    review_overdue = last_review is None or last_review < (
        today - timedelta(days=REVIEW_OVERDUE_DAYS)
    )
    actions = next_best_actions(
        completeness=completeness,
        at_risk=risk,
        review_overdue=review_overdue,
        overdue_follow_up_titles=[a.get("title") or "Follow-up" for a in overdue_follow_ups],
        top_pending_title=next((a.get("title") for a in alerts if a.get("title")), None),
    )
    return {
        "client_name": (row.get("full_name") or "Unknown").strip(),
        "engagement_risk": risk,
        "profile_completeness": completeness,
        "review_overdue": review_overdue,
        "next_best_actions": actions,
        "summary": f"scores computed (risk {risk['score']}, completeness {completeness['score']}%)",
    }


def list_upcoming_alerts(
    ctx: TenantContext, *, client_id: Optional[str] = None, days: int = 30
) -> dict[str, Any]:
    """Pending alerts due in the next N days (and overdue follow-ups)."""
    from app.db import get_cursor

    days = max(1, min(int(days or 30), 365))
    today = datetime.now().date()
    end = today + timedelta(days=days)
    sql = """
        SELECT a.title, a.type, a.priority, a.trigger_date, c.full_name AS client_name
        FROM alerts a
        JOIN clients c ON c.id = a.client_id
        WHERE a.org_id = %s AND a.status = 'PENDING' AND a.trigger_date <= %s
    """
    params: list[Any] = [ctx.org_id, end]
    if client_id:
        sql += " AND a.client_id = %s"
        params.append(client_id)
    sql += " ORDER BY a.trigger_date LIMIT %s"
    params.append(_MAX_ALERT_ROWS)
    with get_cursor(ctx=ctx) as cur:
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
    items = [
        {
            "client": r.get("client_name") or "Unknown",
            "title": r.get("title") or r.get("type"),
            "type": r.get("type"),
            "priority": r.get("priority"),
            "due": r["trigger_date"].isoformat() if r.get("trigger_date") else None,
            "overdue": bool(r.get("trigger_date") and r["trigger_date"] < today),
        }
        for r in rows
    ]
    return {"alerts": items, "summary": f"{len(items)} pending alert(s) within {days} days"}


# ---------------------------------------------------------------------------
# Planner-facing schemas + the single dispatch path
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": (
                "Semantic search over ingested fact-finds and meeting notes. "
                "Use for questions about recommendations, meeting discussions, "
                "protection, estate planning, or anything only in documents."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_structured_context",
            "description": (
                "Load the structured records snapshot: client profiles, review "
                "dates, assets, pending alerts, overdue follow-ups. Use for "
                "book-wide questions, deadlines, reviews, and follow-ups."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_book_analytics",
            "description": (
                "Deterministic book metrics: client count, total AUM, average "
                "risk score, reviews overdue. Use for numeric/aggregate questions."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_client_scores",
            "description": (
                "Deterministic client-intelligence scores for one client: "
                "engagement risk, profile completeness, next-best actions. "
                "Only available when the run is scoped to a client."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_upcoming_alerts",
            "description": "Pending alerts due in the next N days (default 30).",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Window in days (1-365)"},
                },
            },
        },
    },
]

TOOL_NAMES = [schema["function"]["name"] for schema in TOOL_SCHEMAS]


def execute_tool(
    ctx: TenantContext,
    name: str,
    arguments: Optional[dict[str, Any]] = None,
    *,
    client_id: Optional[str] = None,
) -> dict[str, Any]:
    """Run one whitelisted tool. ``client_id`` comes from the run scope (the
    trusted request), never from model output — a planner cannot widen scope."""
    args = arguments or {}
    if name == "search_documents":
        return search_documents(ctx, query=str(args.get("query") or ""), client_id=client_id)
    if name == "get_structured_context":
        return get_structured_context(ctx, client_id=client_id)
    if name == "get_book_analytics":
        return get_book_analytics(ctx)
    if name == "get_client_scores":
        if not client_id:
            return {"error": "This run is not scoped to a client", "summary": "no client scope"}
        return get_client_scores(ctx, client_id=client_id)
    if name == "list_upcoming_alerts":
        days = args.get("days") or 30
        try:
            days = int(days)
        except (TypeError, ValueError):
            days = 30
        return list_upcoming_alerts(ctx, client_id=client_id, days=days)
    raise ValueError(f"Unknown tool {name!r}")
