"""
Ask Jarvis: Hybrid chat. Combines structured data (Postgres: clients, alerts) with RAG (Qdrant).
Query → embed + structured context (parallel when needed) → search Qdrant → LLM synthesize.
Structured context is cached briefly to avoid DB on every query; embedding and DB run in parallel on cache miss.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.db import get_cursor
from app.security import limiter
from app.services.cache import (
    BRIEF_TTL,
    CHAT_TTL,
    STRUCTURED_CTX_TTL,
    get as cache_get,
    hash_query_for_key,
    set_ as cache_set,
)
from app.services.config import QDRANT_COLLECTION
from app.services.vector_store import get_embeddings_openai

# Reusable executor for parallel work (DB + embedding)
_executor = ThreadPoolExecutor(max_workers=4)

router = APIRouter()


class ChatRequest(BaseModel):
    query: str


class SourceOut(BaseModel):
    content: str
    client_name: str
    doc_type: str
    date: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceOut]


class BriefRequest(BaseModel):
    client_id: str


class BriefResponse(BaseModel):
    brief: str
    talking_points: list[str] = []


def _search_qdrant(query_vector: list[float], limit: int = 5, client_id: Optional[str] = None):
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    from app.services.clients import get_qdrant_client

    client = get_qdrant_client()
    query_filter = None
    if client_id:
        query_filter = Filter(must=[FieldCondition(key="client_id", match=MatchValue(value=client_id))])
    results = client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=query_vector,
        limit=limit,
        query_filter=query_filter,
    )
    points = getattr(results, "points", None) or (list(results) if isinstance(results, (list, tuple)) else [])
    return points


def _get_structured_context() -> str:
    """Fetch structured summary from Postgres for hybrid context: clients list, review overdue, upcoming alerts, overdue follow-ups."""
    try:
        today = datetime.now().date()
        review_cutoff = today - timedelta(days=365)
        end_30 = today + timedelta(days=30)
        parts = []
        with get_cursor() as cur:
            # Client list – compact one line per client (cap 50 for speed; enough for list questions)
            cur.execute(
                """
                SELECT c.full_name, c.last_review_date, c.total_assets, c.risk_score, c.retirement_target_age, c.cash_savings
                FROM clients c
                ORDER BY c.full_name
                LIMIT 50
                """
            )
            client_rows = cur.fetchall()
            n_clients = len(client_rows)
            parts.append(f"Total clients: {n_clients}")
            if client_rows:
                # Compact: "Name | review=Y-m-d | assets=X | risk=R | ret_age=A | cash=C"
                client_lines = []
                for r in client_rows:
                    name = (r.get("full_name") or "Unknown").strip()
                    review = r.get("last_review_date")
                    assets = r.get("total_assets")
                    risk = r.get("risk_score")
                    ret_age = r.get("retirement_target_age")
                    cash = r.get("cash_savings")
                    bits = [name]
                    if review is not None:
                        bits.append(f"review={review}")
                    if assets is not None:
                        bits.append(f"assets={assets}")
                    if risk is not None:
                        bits.append(f"risk={risk}")
                    if ret_age is not None:
                        bits.append(f"ret_age={ret_age}")
                    if cash is not None:
                        bits.append(f"cash={cash}")
                    client_lines.append(" | ".join(bits))
                parts.append("Client list:\n" + "\n".join(client_lines))

            # Review overdue (12+ months)
            cur.execute(
                """
                SELECT c.full_name, c.last_review_date
                FROM clients c
                WHERE c.last_review_date IS NULL OR c.last_review_date < %s
                ORDER BY c.last_review_date NULLS FIRST
                LIMIT 50
                """,
                (review_cutoff,),
            )
            rows = cur.fetchall()
            if rows:
                names = [r.get("full_name") or "Unknown" for r in rows]
                parts.append("Clients with no review in 12+ months (review overdue): " + ", ".join(names))

            # Upcoming pending alerts (next 30 days)
            cur.execute(
                """
                SELECT a.title, a.trigger_date, a.type, a.priority, c.full_name AS client_name
                FROM alerts a
                JOIN clients c ON c.id = a.client_id
                WHERE a.trigger_date >= %s AND a.trigger_date <= %s AND a.status = 'PENDING'
                ORDER BY a.trigger_date
                LIMIT 30
                """,
                (today, end_30),
            )
            alert_rows = cur.fetchall()
            if alert_rows:
                lines = [f"- {r.get('client_name') or 'Unknown'}: {r.get('title') or r.get('type')} (due {r.get('trigger_date')}, type={r.get('type')})" for r in alert_rows]
                parts.append("Upcoming pending alerts (next 30 days):\n" + "\n".join(lines))

            # Overdue follow-ups (PENDING FOLLOW_UP with trigger_date in the past)
            cur.execute(
                """
                SELECT a.title, a.trigger_date, a.description, c.full_name AS client_name
                FROM alerts a
                JOIN clients c ON c.id = a.client_id
                WHERE a.trigger_date < %s AND a.status = 'PENDING' AND a.type = 'FOLLOW_UP'
                ORDER BY a.trigger_date
                LIMIT 30
                """,
                (today,),
            )
            overdue_rows = cur.fetchall()
            if overdue_rows:
                lines = [f"- {r.get('client_name') or 'Unknown'}: {r.get('title') or 'Follow-up'} (was due {r.get('trigger_date')}) – {r.get('description') or ''}"[:120] for r in overdue_rows]
                parts.append("Overdue follow-ups (waiting on client – past due):\n" + "\n".join(lines))

            # All PENDING alerts count (for "open action items")
            cur.execute(
                "SELECT COUNT(*) AS n FROM alerts WHERE status = 'PENDING'"
            )
            pending_count = (cur.fetchone() or {}).get("n") or 0
            parts.append(f"Total PENDING alerts (open action items) across all clients: {pending_count}")
        return "\n\n".join(parts)
    except Exception:
        return "Structured data temporarily unavailable."


def _synthesize_openai(rag_context: str, structured_context: str, query: str, model: str) -> str:
    from app.services.clients import get_openai_client
    client = get_openai_client()
    combined = ""
    if structured_context.strip():
        combined += "Structured data (from your client and alert records):\n\n" + structured_context.strip() + "\n\n"
    if rag_context.strip():
        combined += "Context from client documents (meeting notes, fact-finds, etc.):\n\n" + rag_context.strip()
    if not combined.strip():
        combined = "No context available."
    system = (
        "You are Jarvis, a proactive financial assistant for UK financial advisers. Use the provided context to answer the question.\n\n"
        "Structured data includes: a client list (name, last_review_date, total_assets, risk_score, retirement_target_age, cash_savings), "
        "clients with no review in 12+ months, upcoming pending alerts (next 30 days, with type e.g. DEADLINE/OPPORTUNITY/FOLLOW_UP), "
        "overdue follow-ups (waiting on client, past due), and total PENDING alerts count. Use this for: review overdue, who to chase, "
        "approaching retirement, high net worth (total_assets), open action items, birthdays (if DOB/OPPORTUNITY alerts appear in upcoming alerts).\n\n"
        "Document excerpts are from fact-finds and meeting notes. Use them for: recommendations made, rationale, exact wording, "
        "ISA/allowances, protection gaps, business owners, education planning, estate planning, compliance, and anything not in the structured list.\n\n"
        "If the context does not contain relevant information, say so clearly. Cite client names or document sources when possible."
    )
    r = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"{combined}\n\nQuestion: {query}"},
        ],
        max_tokens=1024,
    )
    return (r.choices[0].message.content or "").strip()


@router.post("/", response_model=ChatResponse)
@limiter.limit("30/minute")
def chat(request: Request, body: ChatRequest):
    """
    Ask Jarvis: embed query + structured context (parallel when cache miss), search Qdrant, synthesize with LLM.
    Responses cached by query hash; structured context cached briefly to avoid DB every time.
    """
    query = (body.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    cache_key = f"chat:{hash_query_for_key(query)}"
    cached = cache_get(cache_key)
    if cached is not None and isinstance(cached, dict):
        sources = [SourceOut(**s) for s in (cached.get("sources") or []) if isinstance(s, dict)]
        return ChatResponse(answer=cached.get("answer", ""), sources=sources)

    # Run structured context (from cache or DB) and embedding in parallel to save latency
    cache_key_ctx = "chat:structured_ctx"
    structured_cached = cache_get(cache_key_ctx)
    if isinstance(structured_cached, str) and structured_cached:
        structured_context = structured_cached
        vec = get_embeddings_openai([query])
    else:
        fut_ctx = _executor.submit(_get_structured_context)
        fut_vec = _executor.submit(get_embeddings_openai, [query])
        structured_context = fut_ctx.result()
        cache_set(cache_key_ctx, structured_context, STRUCTURED_CTX_TTL)
        vec = fut_vec.result()
    if not vec:
        raise HTTPException(status_code=500, detail="Embedding failed")
    query_vector = vec[0]

    points = _search_qdrant(query_vector, limit=6)
    rag_context = ""
    sources_out = []
    if points:
        context_parts = []
        for i, pt in enumerate(points):
            payload = getattr(pt, "payload", None) or {}
            content = (payload.get("content") or "")[:1800]
            client_name = payload.get("client_name") or "Unknown"
            doc_type = payload.get("doc_type") or ""
            date = payload.get("date") or ""
            context_parts.append(f"[{i + 1}] (Client: {client_name}, {doc_type}, {date})\n{content}")
            sources_out.append(
                SourceOut(content=content[:300] + ("..." if len(content) > 300 else ""), client_name=client_name, doc_type=doc_type, date=date)
            )
        rag_context = "\n\n---\n\n".join(context_parts)

    model = os.environ.get("LLM_MODEL", "gpt-4o")
    answer = _synthesize_openai(rag_context, structured_context, query, model)

    if not answer and not rag_context.strip() and not structured_context.strip():
        answer = "I don't have any client data or documents indexed yet. Upload PDFs or Word documents in Ingestion and ensure you have clients and alerts in the system."

    out = ChatResponse(answer=answer or "I couldn't find a clear answer from the available context.", sources=sources_out)
    cache_set(cache_key, {"answer": out.answer, "sources": [s.model_dump() for s in out.sources]}, CHAT_TTL)
    return out


def _generate_brief(client_id: str) -> tuple[str, list[str]]:
    """Build pre-meeting brief for one client: structured data + RAG chunks, then LLM one-pager + talking points."""
    client_name = "Unknown"
    structured_parts = []
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, full_name, last_review_date, risk_score, total_assets FROM clients WHERE id = %s",
            (client_id,),
        )
        row = cur.fetchone()
    if not row:
        return "Client not found.", []
    client_name = (row.get("full_name") or "Unknown").strip()
    last_review = row.get("last_review_date")
    risk = row.get("risk_score")
    assets = row.get("total_assets")
    structured_parts.append(f"Client: {client_name}")
    if last_review:
        structured_parts.append(f"Last review: {last_review}")
    if risk is not None:
        structured_parts.append(f"Risk score: {risk}")
    if assets is not None:
        structured_parts.append(f"Total assets: {assets}")

    today = datetime.now().date()
    end = today + timedelta(days=90)
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.title, a.trigger_date, a.type, a.description, a.status
            FROM alerts a
            WHERE a.client_id = %s AND a.trigger_date >= %s AND a.trigger_date <= %s
            ORDER BY a.trigger_date
            LIMIT 15
            """,
            (client_id, today, end),
        )
        alert_rows = cur.fetchall()
    if alert_rows:
        lines = [f"- {r.get('title') or r.get('type')} (due {r.get('trigger_date')}): {r.get('description') or ''}"[:120] for r in alert_rows]
        structured_parts.append("Upcoming alerts (next 90 days):\n" + "\n".join(lines))

    rag_parts = []
    try:
        vec = get_embeddings_openai([client_name + " meeting notes fact find"])
        if vec:
            points = _search_qdrant(vec[0], limit=10, client_id=client_id)
            for pt in points:
                payload = getattr(pt, "payload", None) or {}
                content = (payload.get("content") or "")[:1500]
                doc_type = payload.get("doc_type") or ""
                date = payload.get("date") or ""
                if content:
                    rag_parts.append(f"[{doc_type}, {date}]\n{content}")
    except Exception:
        pass
    rag_context = "\n\n---\n\n".join(rag_parts) if rag_parts else "No document excerpts found for this client."

    structured_text = "\n".join(structured_parts)
    combined = f"Structured data for {client_name}:\n{structured_text}\n\nDocument excerpts (meeting notes, fact-finds):\n{rag_context}"

    system = (
        "You are Jarvis, a proactive financial assistant. Write a concise one-page pre-meeting brief for the adviser. "
        "Use the provided client data and document excerpts. Include: (1) Key facts about the client, "
        "(2) Recent or upcoming items (reviews, alerts, deadlines), (3) Any commitments or follow-ups mentioned in documents. "
        "Use clear headings and bullet points. Keep it to one page; be scannable.\n\n"
        "IMPORTANT: After the brief, on a new line write exactly ---TALKING_POINTS--- (three hyphens, the word TALKING_POINTS, three hyphens). "
        "Then list 3-4 suggested discussion points for the adviser to cover in the meeting (short phrases, one per line). "
        "Each line should be a single actionable point, e.g. 'Pension contribution increase – recap recommendation' or 'Lynne early retirement – agree phased reduction'."
    )
    # Pre-meeting brief uses a lighter, faster model by default (override with BRIEF_LLM_MODEL or LLM_MODEL)
    model = os.environ.get("BRIEF_LLM_MODEL") or os.environ.get("LLM_MODEL") or "gpt-4o-mini"
    from app.services.clients import get_openai_client
    client = get_openai_client()
    r = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": combined},
        ],
        max_tokens=1024,
    )
    raw = (r.choices[0].message.content or "").strip()
    talking_points: list[str] = []
    if "---TALKING_POINTS---" in raw:
        brief_part, points_part = raw.split("---TALKING_POINTS---", 1)
        brief_text = brief_part.strip()
        for line in points_part.strip().splitlines():
            line = line.strip().lstrip("-•* ").strip()
            if line:
                talking_points.append(line)
        talking_points = talking_points[:5]  # cap at 5
    else:
        brief_text = raw
    return brief_text, talking_points


@router.post("/brief", response_model=BriefResponse)
@limiter.limit("30/minute")
def post_brief(request: Request, body: BriefRequest):
    """Generate a pre-meeting brief for the given client (structured data + RAG). Cached by client_id. Includes suggested talking points."""
    client_id = (body.client_id or "").strip()
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id is required")
    cache_key = f"brief:{client_id}"
    cached = cache_get(cache_key)
    if cached is not None and isinstance(cached, dict):
        return BriefResponse(
            brief=cached.get("brief") or "",
            talking_points=cached.get("talking_points") or [],
        )
    brief_text, talking_points = _generate_brief(client_id)
    cache_set(cache_key, {"brief": brief_text, "talking_points": talking_points}, BRIEF_TTL)
    return BriefResponse(brief=brief_text, talking_points=talking_points)
