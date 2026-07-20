"""
Ask Jarvis: Hybrid chat. Combines structured data (Postgres: clients, alerts) with RAG (Qdrant).
Query → embed + structured context (parallel when needed) → search Qdrant → LLM synthesize.
Structured context is cached briefly to avoid DB on every query; embedding and DB run in parallel on cache miss.

Tenancy: the executor-submitted helpers receive the TenantContext explicitly —
contextvars do not propagate into ThreadPoolExecutor threads — and every SQL,
cache, and vector-search call is org-scoped.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.context import TenantContext
from app.db import get_cursor
from app.deps import current_tenant
from app.security import limiter, llm_daily_limit
from app.services import audit
from app.services import conversations
from app.services.cache import (
    BRIEF_TTL,
    CHAT_TTL,
    STRUCTURED_CTX_TTL,
    get_scoped as cache_get,
    hash_query_for_key,
    set_scoped as cache_set,
)
from app.services.llm import complete_with_system, resolve_model
from app.services.prompts import (
    BRIEF_SYSTEM,
    CHAT_SYSTEM,
    PROMPT_VERSION,
    brief_user_message,
    chat_user_message,
)
from app.services.rag_context import retrieve_for_brief, retrieve_for_chat
from app.services.safety import sanitize_user_query

_executor = ThreadPoolExecutor(max_workers=4)

router = APIRouter()


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    client_id: Optional[str] = Field(default=None, max_length=64)
    conversation_id: Optional[str] = Field(default=None, max_length=64)


class SourceOut(BaseModel):
    ref: int = 0
    content: str
    client_name: str
    doc_type: str
    date: str
    relevance: Optional[float] = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
    conversation_id: Optional[str] = None


class BriefRequest(BaseModel):
    client_id: str = Field(..., min_length=1, max_length=64)
    # True = regenerate: bypass the cached brief (the fresh result still
    # replaces the cache entry so subsequent loads stay fast).
    refresh: bool = False


class BriefResponse(BaseModel):
    brief: str
    talking_points: list[str] = []
    sources: list[SourceOut] = []


def _fmt_gbp(value) -> str:
    if value is None:
        return ""
    return f"£{float(value):,.0f}"


def _get_structured_context(ctx: TenantContext, client_id: Optional[str] = None) -> str:
    """Fetch compact structured summary from Postgres for hybrid context."""
    try:
        today = datetime.now().date()
        review_cutoff = today - timedelta(days=365)
        end_30 = today + timedelta(days=30)
        org_id = ctx.org_id
        parts = []
        with get_cursor(ctx=ctx) as cur:
            if client_id:
                cur.execute(
                    """
                    SELECT c.full_name, c.last_review_date, c.total_assets, c.risk_score,
                           c.retirement_target_age, c.cash_savings
                    FROM clients c WHERE c.id = %s AND c.org_id = %s
                    """,
                    (client_id, org_id),
                )
                row = cur.fetchone()
                if not row:
                    return "Client not found."
                name = (row.get("full_name") or "Unknown").strip()
                bits = [name]
                if row.get("last_review_date") is not None:
                    bits.append(f"review={row['last_review_date']}")
                if row.get("total_assets") is not None:
                    bits.append(f"assets={_fmt_gbp(row['total_assets'])}")
                if row.get("risk_score") is not None:
                    bits.append(f"risk={row['risk_score']}/10")
                if row.get("retirement_target_age") is not None:
                    bits.append(f"ret_age={row['retirement_target_age']}")
                if row.get("cash_savings") is not None:
                    bits.append(f"cash={_fmt_gbp(row['cash_savings'])}")
                parts.append("Focused client: " + " | ".join(bits))
                if row.get("last_review_date") is None or row["last_review_date"] < review_cutoff:
                    parts.append(f"{name}: annual review overdue (12+ months).")
            else:
                cur.execute(
                    """
                    SELECT c.full_name, c.last_review_date, c.total_assets, c.risk_score
                    FROM clients c
                    WHERE c.org_id = %s
                    ORDER BY c.full_name
                    LIMIT 30
                    """,
                    (org_id,),
                )
                client_rows = cur.fetchall()
                parts.append(f"Clients in book: {len(client_rows)}")
                if client_rows:
                    client_lines = []
                    for r in client_rows:
                        name = (r.get("full_name") or "Unknown").strip()
                        bits = [name]
                        if r.get("last_review_date") is not None:
                            bits.append(f"review={r['last_review_date']}")
                        if r.get("total_assets") is not None:
                            bits.append(f"assets={_fmt_gbp(r['total_assets'])}")
                        client_lines.append(" | ".join(bits))
                    parts.append("\n".join(client_lines))

                cur.execute(
                    """
                    SELECT c.full_name
                    FROM clients c
                    WHERE c.org_id = %s
                      AND (c.last_review_date IS NULL OR c.last_review_date < %s)
                    ORDER BY c.last_review_date NULLS FIRST
                    LIMIT 20
                    """,
                    (org_id, review_cutoff),
                )
                rows = cur.fetchall()
                if rows:
                    names = [(r.get("full_name") or "Unknown") for r in rows]
                    parts.append("Review overdue: " + ", ".join(names))

            alert_sql = """
                SELECT a.title, a.trigger_date, a.type, a.priority, c.full_name AS client_name
                FROM alerts a
                JOIN clients c ON c.id = a.client_id
                WHERE a.org_id = %s AND a.trigger_date >= %s AND a.trigger_date <= %s
                  AND a.status = 'PENDING'
            """
            alert_params: list = [org_id, today, end_30]
            if client_id:
                alert_sql += " AND a.client_id = %s"
                alert_params.append(client_id)
            alert_sql += " ORDER BY a.trigger_date LIMIT 20"
            cur.execute(alert_sql, tuple(alert_params))
            alert_rows = cur.fetchall()
            if alert_rows:
                lines = [
                    f"- {r.get('client_name') or 'Unknown'}: {r.get('title') or r.get('type')} "
                    f"(due {r.get('trigger_date')}, {r.get('priority')})"
                    for r in alert_rows
                ]
                parts.append("Pending alerts (30 days):\n" + "\n".join(lines))

            follow_sql = """
                SELECT a.title, a.trigger_date, c.full_name AS client_name
                FROM alerts a
                JOIN clients c ON c.id = a.client_id
                WHERE a.org_id = %s AND a.trigger_date < %s AND a.status = 'PENDING'
                  AND a.type = 'FOLLOW_UP'
            """
            follow_params: list = [org_id, today]
            if client_id:
                follow_sql += " AND a.client_id = %s"
                follow_params.append(client_id)
            follow_sql += " ORDER BY a.trigger_date LIMIT 15"
            cur.execute(follow_sql, tuple(follow_params))
            overdue_rows = cur.fetchall()
            if overdue_rows:
                lines = [
                    f"- {r.get('client_name') or 'Unknown'}: {r.get('title') or 'Follow-up'} "
                    f"(was due {r.get('trigger_date')})"
                    for r in overdue_rows
                ]
                parts.append("Overdue follow-ups:\n" + "\n".join(lines))

            if client_id:
                cur.execute(
                    "SELECT COUNT(*) AS n FROM alerts WHERE client_id = %s AND org_id = %s AND status = 'PENDING'",
                    (client_id, org_id),
                )
            else:
                cur.execute(
                    "SELECT COUNT(*) AS n FROM alerts WHERE org_id = %s AND status = 'PENDING'",
                    (org_id,),
                )
            pending_count = (cur.fetchone() or {}).get("n") or 0
            parts.append(f"Total pending alerts: {pending_count}")
        return "\n\n".join(parts)
    except Exception:
        return "Structured data temporarily unavailable."


@router.post("/", response_model=ChatResponse)
@limiter.limit("30/minute")
def chat(request: Request, body: ChatRequest, ctx: TenantContext = Depends(current_tenant)):
    """
    Ask Jarvis: embed query + structured context (parallel when cache miss), search Qdrant, synthesize with LLM.
    Responses cached by query hash; structured context cached briefly to avoid DB every time.
    """
    query = sanitize_user_query(body.query or "")
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    client_id = (body.client_id or "").strip() or None
    if client_id:
        with get_cursor() as cur:
            cur.execute(
                "SELECT id FROM clients WHERE id = %s AND org_id = %s", (client_id, ctx.org_id)
            )
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Client not found")

    # Resolve the conversation thread: reuse the supplied one (must be owned by
    # this user in this workspace) or start a new one.
    conversation_id = (body.conversation_id or "").strip() or None
    if conversation_id and not conversations.exists(conversation_id):
        conversation_id = None
    if conversation_id is None:
        conversation_id = conversations.create(client_id=client_id)
    prior_messages = conversations.get_messages(conversation_id)
    history = conversations.format_history(prior_messages)

    user_prefix = ctx.user_id or ctx.role
    scope_key = client_id or "all"
    # Only cache stateless (first-turn) queries; follow-ups depend on history.
    use_cache = not history
    cache_key = f"chat:{PROMPT_VERSION}:{user_prefix}:{hash_query_for_key(query)}:{scope_key}"
    if use_cache:
        cached = cache_get(cache_key)
        if cached is not None and isinstance(cached, dict):
            conversations.add_message(conversation_id, "user", query)
            conversations.add_message(conversation_id, "assistant", cached.get("answer", ""))
            sources = [SourceOut(**s) for s in (cached.get("sources") or []) if isinstance(s, dict)]
            return ChatResponse(
                answer=cached.get("answer", ""), sources=sources, conversation_id=conversation_id
            )

    cache_key_ctx = f"chat:structured_ctx:{scope_key}"
    structured_cached = cache_get(cache_key_ctx)
    if isinstance(structured_cached, str) and structured_cached:
        structured_context = structured_cached
        rag_context, source_dicts = retrieve_for_chat(query, org_id=ctx.org_id, client_id=client_id)
    else:
        # Pass ctx explicitly: contextvars do not cross into executor threads.
        fut_ctx = _executor.submit(_get_structured_context, ctx, client_id)
        fut_rag = _executor.submit(retrieve_for_chat, query, org_id=ctx.org_id, client_id=client_id)
        structured_context = fut_ctx.result()
        cache_set(cache_key_ctx, structured_context, STRUCTURED_CTX_TTL)
        rag_context, source_dicts = fut_rag.result()

    model = resolve_model("chat")
    answer = complete_with_system(
        system=CHAT_SYSTEM,
        user=chat_user_message(
            structured=structured_context, documents=rag_context, query=query, history=history
        ),
        max_tokens=900,
        model=model,
        purpose="chat",
    )

    if not answer and not rag_context.strip() and not structured_context.strip():
        answer = (
            "I don't have any client data or documents indexed yet. "
            "Upload PDFs or Word documents in Ingestion and ensure you have clients and alerts in the system."
        )

    sources_out = [SourceOut(**s) for s in source_dicts]
    final_answer = answer or "I couldn't find a clear answer from the available context."
    out = ChatResponse(
        answer=final_answer,
        sources=sources_out,
        conversation_id=conversation_id,
    )
    if use_cache:
        cache_set(cache_key, {"answer": out.answer, "sources": [s.model_dump() for s in out.sources]}, CHAT_TTL)
    conversations.add_message(conversation_id, "user", query)
    conversations.add_message(conversation_id, "assistant", final_answer)
    audit.record_event(
        action="ai.chat.answered",
        resource_type="conversation",
        resource_id=conversation_id,
        client_id=client_id,
        metadata={"sources": len(sources_out), "first_turn": use_cache},
        model=model,
        prompt_version=PROMPT_VERSION,
        actor_type="ai",
    )
    return out


def _generate_brief(ctx: TenantContext, client_id: str) -> tuple[str, list[str], list[dict]]:
    """Build pre-meeting brief: structured data + RAG chunks, then LLM one-pager + talking points."""
    structured_parts: list[str] = []
    alert_titles: list[str] = []

    with get_cursor(ctx=ctx) as cur:
        cur.execute(
            "SELECT id, full_name, last_review_date, risk_score, total_assets, cash_savings"
            " FROM clients WHERE id = %s AND org_id = %s",
            (client_id, ctx.org_id),
        )
        row = cur.fetchone()
        if not row:
            return "Client not found.", [], []

        client_name = (row.get("full_name") or "Unknown").strip()
        if row.get("last_review_date"):
            structured_parts.append(f"Last review: {row['last_review_date']}")
        if row.get("risk_score") is not None:
            structured_parts.append(f"Risk score: {row['risk_score']}/10")
        if row.get("total_assets") is not None:
            structured_parts.append(f"Total assets: {_fmt_gbp(row['total_assets'])}")
        if row.get("cash_savings") is not None:
            structured_parts.append(f"Cash savings: {_fmt_gbp(row['cash_savings'])}")

        today = datetime.now().date()
        end = today + timedelta(days=90)
        cur.execute(
            """
            SELECT a.title, a.trigger_date, a.type, a.description
            FROM alerts a
            WHERE a.client_id = %s AND a.org_id = %s
              AND a.trigger_date >= %s AND a.trigger_date <= %s
              AND a.status = 'PENDING'
            ORDER BY a.trigger_date
            LIMIT 12
            """,
            (client_id, ctx.org_id, today, end),
        )
        alert_rows = cur.fetchall()
    if alert_rows:
        lines = []
        for r in alert_rows:
            title = r.get("title") or r.get("type") or "Alert"
            alert_titles.append(str(title))
            desc = (r.get("description") or "")[:80]
            lines.append(f"- {title} (due {r.get('trigger_date')}): {desc}")
        structured_parts.append("Open alerts (90 days):\n" + "\n".join(lines))

    try:
        rag_context, source_dicts = retrieve_for_brief(
            client_name, alert_titles, org_id=ctx.org_id, client_id=client_id
        )
    except Exception:
        rag_context = ""
        source_dicts = []

    structured_text = "\n".join(structured_parts) or "No structured data on file."
    model = resolve_model("brief")
    raw = complete_with_system(
        system=BRIEF_SYSTEM,
        user=brief_user_message(
            client_name=client_name,
            structured=structured_text,
            documents=rag_context,
        ),
        max_tokens=1400,
        model=model,
        purpose="brief",
    )

    talking_points: list[str] = []
    if "---TALKING_POINTS---" in raw:
        brief_part, points_part = raw.split("---TALKING_POINTS---", 1)
        brief_text = brief_part.strip()
        for line in points_part.strip().splitlines():
            line = line.strip().lstrip("-•* ").strip()
            if line:
                talking_points.append(line)
        talking_points = talking_points[:5]
    else:
        brief_text = raw
    audit.record(
        kind="brief",
        client_id=client_id,
        client_name=client_name,
        model=model,
        output=brief_text,
        prompt_version=PROMPT_VERSION,
        ctx=ctx,
    )
    return brief_text, talking_points, source_dicts


@router.post("/brief", response_model=BriefResponse)
@limiter.limit("30/minute")
@llm_daily_limit
def post_brief(request: Request, body: BriefRequest, ctx: TenantContext = Depends(current_tenant)):
    """Generate a pre-meeting brief for the given client (structured data + RAG). Cached by client_id."""
    client_id = (body.client_id or "").strip()
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id is required")
    with get_cursor() as cur:
        cur.execute(
            "SELECT id FROM clients WHERE id = %s AND org_id = %s", (client_id, ctx.org_id)
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Client not found")
    cache_key = f"brief:{PROMPT_VERSION}:{client_id}"
    if not body.refresh:
        cached = cache_get(cache_key)
        if cached is not None and isinstance(cached, dict):
            sources = [SourceOut(**s) for s in (cached.get("sources") or []) if isinstance(s, dict)]
            return BriefResponse(
                brief=cached.get("brief") or "",
                talking_points=cached.get("talking_points") or [],
                sources=sources,
            )
    brief_text, talking_points, source_dicts = _generate_brief(ctx, client_id)
    sources_out = [SourceOut(**s) for s in source_dicts]
    cache_set(
        cache_key,
        {
            "brief": brief_text,
            "talking_points": talking_points,
            "sources": [s.model_dump() for s in sources_out],
        },
        BRIEF_TTL,
    )
    return BriefResponse(brief=brief_text, talking_points=talking_points, sources=sources_out)
