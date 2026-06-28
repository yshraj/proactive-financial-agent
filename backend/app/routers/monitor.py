"""
Monitor / Pulse API: alerts by simulated date for the dashboard (time-travel).
GET /api/monitor/pulse?simulated_date=YYYY-MM-DD returns alerts in the next 30 days + KPI counts.
POST /api/monitor/draft-email: generate personalised email draft for an alert (LLM).
"""
import json
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.db import get_cursor
from app.security import limiter
from app.services.cache import DRAFT_EMAIL_TTL, delete as cache_delete, get as cache_get, set_ as cache_set

router = APIRouter()


class ClientOut(BaseModel):
    id: str
    full_name: str


class ClientsListResponse(BaseModel):
    clients: list[ClientOut]


@router.get("/clients", response_model=ClientsListResponse)
def get_clients():
    """List all clients (id, full_name) for dropdowns e.g. Pre-meeting brief."""
    with get_cursor() as cur:
        cur.execute("SELECT id, full_name FROM clients ORDER BY full_name")
        rows = cur.fetchall()
    clients = [
        ClientOut(id=str(r["id"]), full_name=(r.get("full_name") or "Unknown").strip())
        for r in rows
    ]
    return ClientsListResponse(clients=clients)


class AlertOut(BaseModel):
    id: str
    client_id: str
    client_name: str
    trigger_date: str
    type: str
    priority: str
    title: Optional[str]
    description: Optional[str]
    status: str


class PulseResponse(BaseModel):
    alerts: list[AlertOut]
    total: int
    high_risk: int
    deadlines: int
    client_count: int
    overdue_follow_ups: list[AlertOut] = []


@router.get("/pulse", response_model=PulseResponse)
def get_pulse(
    simulated_date: str = Query(..., description="YYYY-MM-DD"),
):
    """
    Alerts whose trigger_date is in [simulated_date, simulated_date + 30 days], status PENDING.
    Joins clients for display name. Also returns KPI counts for the dashboard.
    """
    try:
        base = datetime.strptime(simulated_date, "%Y-%m-%d").date()
    except ValueError:
        base = datetime.now().date()
    end = base + timedelta(days=30)

    review_cutoff = base - timedelta(days=365)

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.id, a.client_id, a.trigger_date, a.type, a.priority, a.title, a.description, a.status,
                   c.full_name AS client_name
            FROM alerts a
            JOIN clients c ON c.id = a.client_id
            WHERE a.trigger_date >= %s AND a.trigger_date <= %s AND a.status = 'PENDING'
            ORDER BY a.trigger_date, a.priority DESC
            """,
            (base, end),
        )
        rows = cur.fetchall()

        # Dynamic "Review Overdue" (Consumer Duty): clients with no review in 365+ days
        cur.execute(
            """
            SELECT c.id AS client_id, c.full_name AS client_name, c.last_review_date
            FROM clients c
            WHERE c.last_review_date IS NULL OR c.last_review_date < %s
            ORDER BY c.last_review_date NULLS FIRST
            """,
            (review_cutoff,),
        )
        review_overdue_rows = cur.fetchall()

        cur.execute("SELECT COUNT(*) AS n FROM clients")
        client_count = cur.fetchone()["n"] or 0

        # Overdue follow-ups: PENDING FOLLOW_UP alerts whose trigger_date is before simulated date
        cur.execute(
            """
            SELECT a.id, a.client_id, a.trigger_date, a.type, a.priority, a.title, a.description, a.status,
                   c.full_name AS client_name
            FROM alerts a
            JOIN clients c ON c.id = a.client_id
            WHERE a.trigger_date < %s AND a.status = 'PENDING' AND a.type = 'FOLLOW_UP'
            ORDER BY a.trigger_date ASC
            """,
            (base,),
        )
        overdue_follow_up_rows = cur.fetchall()

    alerts = [
        AlertOut(
            id=str(r["id"]),
            client_id=str(r["client_id"]),
            client_name=(r["client_name"] or "Unknown").strip(),
            trigger_date=r["trigger_date"].isoformat() if r["trigger_date"] else "",
            type=(r["type"] or ""),
            priority=(r["priority"] or ""),
            title=r["title"],
            description=r["description"],
            status=(r["status"] or "PENDING"),
        )
        for r in rows
    ]

    # Append synthetic REVIEW_OVERDUE alerts (trigger_date = simulated date so they appear "due now")
    for r in review_overdue_rows:
        cid = str(r["client_id"])
        alerts.append(
            AlertOut(
                id=f"review-overdue-{cid}",
                client_id=cid,
                client_name=(r["client_name"] or "Unknown").strip(),
                trigger_date=base.isoformat(),
                type="REVIEW_OVERDUE",
                priority="HIGH",
                title="Annual review overdue",
                description="No review in 12+ months. Consumer Duty requires demonstrating ongoing value.",
                status="PENDING",
            )
        )

    # Sort by trigger_date then priority (HIGH first)
    def sort_key(a: AlertOut):
        return (a.trigger_date, 0 if a.priority == "HIGH" else 1 if a.priority == "MEDIUM" else 2)
    alerts.sort(key=sort_key)

    high_risk = sum(1 for a in alerts if a.priority == "HIGH")
    deadlines = sum(1 for a in alerts if a.type == "DEADLINE")

    overdue_follow_ups = [
        AlertOut(
            id=str(r["id"]),
            client_id=str(r["client_id"]),
            client_name=(r["client_name"] or "Unknown").strip(),
            trigger_date=r["trigger_date"].isoformat() if r["trigger_date"] else "",
            type=(r["type"] or "FOLLOW_UP"),
            priority=(r["priority"] or "MEDIUM"),
            title=r["title"],
            description=r["description"],
            status=(r["status"] or "PENDING"),
        )
        for r in overdue_follow_up_rows
    ]

    return PulseResponse(
        alerts=alerts,
        total=len(alerts),
        high_risk=high_risk,
        deadlines=deadlines,
        client_count=client_count,
        overdue_follow_ups=overdue_follow_ups,
    )


class AlertsListResponse(BaseModel):
    alerts: list[AlertOut]


@router.get("/alerts", response_model=AlertsListResponse)
def get_alerts(
    simulated_date: Optional[str] = Query(None, description="YYYY-MM-DD (default: today)"),
    days: int = Query(90, ge=1, le=730, description="Window: simulated_date to +days"),
    type_filter: Optional[str] = Query(None, alias="type", description="Filter by type"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: PENDING, COMPLETED, or omit for all"),
):
    """
    All alerts in [simulated_date, simulated_date + days], with optional type/priority/status filters.
    Includes synthetic REVIEW_OVERDUE for clients with no review in 12+ months (PENDING only).
    """
    if simulated_date:
        try:
            base = datetime.strptime(simulated_date, "%Y-%m-%d").date()
        except ValueError:
            base = datetime.now().date()
    else:
        base = datetime.now().date()
    end = base + timedelta(days=days)
    review_cutoff = base - timedelta(days=365)

    with get_cursor() as cur:
        sql = """
            SELECT a.id, a.client_id, a.trigger_date, a.type, a.priority, a.title, a.description, a.status,
                   c.full_name AS client_name
            FROM alerts a
            JOIN clients c ON c.id = a.client_id
            WHERE a.trigger_date >= %s AND a.trigger_date <= %s
            """
        params: list = [base, end]
        if type_filter:
            sql += " AND a.type = %s"
            params.append(type_filter)
        if priority:
            sql += " AND a.priority = %s"
            params.append(priority)
        if status_filter:
            sql += " AND a.status = %s"
            params.append(status_filter.upper())
        sql += " ORDER BY a.trigger_date, a.priority DESC"
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()

        cur.execute(
            """
            SELECT c.id AS client_id, c.full_name AS client_name
            FROM clients c
            WHERE c.last_review_date IS NULL OR c.last_review_date < %s
            """,
            (review_cutoff,),
        )
        review_overdue_rows = cur.fetchall()

    alerts = [
        AlertOut(
            id=str(r["id"]),
            client_id=str(r["client_id"]),
            client_name=(r["client_name"] or "Unknown").strip(),
            trigger_date=r["trigger_date"].isoformat() if r["trigger_date"] else "",
            type=(r["type"] or ""),
            priority=(r["priority"] or ""),
            title=r["title"],
            description=r["description"],
            status=(r["status"] or "PENDING"),
        )
        for r in rows
    ]

    for r in review_overdue_rows:
        cid = str(r["client_id"])
        if status_filter and status_filter.upper() == "COMPLETED":
            continue
        if type_filter and type_filter != "REVIEW_OVERDUE":
            continue
        if priority and priority != "HIGH":
            continue
        alerts.append(
            AlertOut(
                id=f"review-overdue-{cid}",
                client_id=cid,
                client_name=(r["client_name"] or "Unknown").strip(),
                trigger_date=base.isoformat(),
                type="REVIEW_OVERDUE",
                priority="HIGH",
                title="Annual review overdue",
                description="No review in 12+ months. Consumer Duty requires demonstrating ongoing value.",
                status="PENDING",
            )
        )

    def sort_key(a: AlertOut):
        return (a.trigger_date, 0 if a.priority == "HIGH" else 1 if a.priority == "MEDIUM" else 2)
    alerts.sort(key=sort_key)

    return AlertsListResponse(alerts=alerts)


@router.get("/completed", response_model=AlertsListResponse)
def get_completed(
    limit: int = Query(10, ge=1, le=50, description="Max number of recently completed alerts"),
):
    """
    Recently completed (marked as done) alerts, ordered by updated_at descending.
    For display on the dashboard without Draft Email option.
    """
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.id, a.client_id, a.trigger_date, a.type, a.priority, a.title, a.description, a.status,
                   c.full_name AS client_name
            FROM alerts a
            JOIN clients c ON c.id = a.client_id
            WHERE a.status = 'COMPLETED'
            ORDER BY a.updated_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
    alerts = [
        AlertOut(
            id=str(r["id"]),
            client_id=str(r["client_id"]),
            client_name=(r["client_name"] or "Unknown").strip(),
            trigger_date=r["trigger_date"].isoformat() if r["trigger_date"] else "",
            type=(r["type"] or ""),
            priority=(r["priority"] or ""),
            title=r["title"],
            description=r["description"],
            status=(r["status"] or "COMPLETED"),
        )
        for r in rows
    ]
    return AlertsListResponse(alerts=alerts)


class AlertStatusUpdate(BaseModel):
    status: str  # e.g. 'COMPLETED'


@router.patch("/alerts/{alert_id}/status", response_model=AlertOut)
def update_alert_status(alert_id: str, body: AlertStatusUpdate):
    """
    Update alert status (e.g. mark as COMPLETED). Only for real alerts (UUID); synthetic review-overdue cannot be updated.
    """
    if alert_id.startswith("review-overdue-"):
        raise HTTPException(status_code=400, detail="Synthetic review-overdue alerts cannot be marked done; they reflect client review status.")
    if body.status.upper() not in ("COMPLETED", "DONE", "CANCELLED", "PENDING"):
        raise HTTPException(status_code=400, detail="Invalid status. Use COMPLETED, DONE, CANCELLED, or PENDING.")
    status = "COMPLETED" if body.status.upper() in ("COMPLETED", "DONE") else body.status.upper()
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE alerts SET status = %s, updated_at = NOW() WHERE id = %s RETURNING id, client_id, trigger_date, type, priority, title, description, status",
            (status, alert_id),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    cache_delete(f"draft:{alert_id}")
    with get_cursor() as cur:
        cur.execute("SELECT full_name FROM clients WHERE id = %s", (row["client_id"],))
        client_row = cur.fetchone()
    client_name = (client_row.get("full_name") or "Unknown").strip() if client_row else "Unknown"
    return AlertOut(
        id=str(row["id"]),
        client_id=str(row["client_id"]),
        client_name=client_name,
        trigger_date=row["trigger_date"].isoformat() if row["trigger_date"] else "",
        type=(row["type"] or ""),
        priority=(row["priority"] or ""),
        title=row["title"],
        description=row["description"],
        status=(row["status"] or status),
    )


class DraftEmailRequest(BaseModel):
    alert_id: str


class DraftEmailResponse(BaseModel):
    draft: str


def _call_llm_draft(client_name: str, title: str, description: str, action_payload: Optional[dict], model: str) -> str:
    from app.services.clients import get_openai_client
    payload_str = json.dumps(action_payload, indent=2) if action_payload else "{}"
    prompt = f"""You are a financial adviser's assistant. Write a short, professional email draft to the client about the following alert.
Client name: {client_name}
Alert title: {title or 'Follow-up'}
Alert description: {description or 'No description.'}
Optional action context (use if relevant): {payload_str}

Write only the email body (2–4 short paragraphs). Use a professional but friendly tone. Do not include subject line or greetings/signatures unless asked. Output plain text only."""
    client = get_openai_client()
    r = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
    )
    return (r.choices[0].message.content or "").strip()


@router.post("/draft-email", response_model=DraftEmailResponse)
@limiter.limit("30/minute")
def draft_email(request: Request, body: DraftEmailRequest):
    """Generate a personalised email draft for an alert using the LLM. Cached by alert_id; invalidated when alert status is updated."""
    alert_id = body.alert_id
    cache_key = f"draft:{alert_id}"
    draft = cache_get(cache_key)
    if draft is not None:
        return DraftEmailResponse(draft=draft)

    if alert_id.startswith("review-overdue-"):
        client_id = alert_id.replace("review-overdue-", "", 1)
        with get_cursor() as cur:
            cur.execute(
                "SELECT full_name FROM clients WHERE id = %s",
                (client_id,),
            )
            row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Client not found")
        client_name = (row.get("full_name") or "Client").strip()
        title = "Annual review overdue"
        description = "No review in 12+ months. Consumer Duty requires demonstrating ongoing value."
        model = os.environ.get("LLM_MODEL", "gpt-4o")
        draft = _call_llm_draft(client_name, title, description, None, model)
        cache_set(cache_key, draft, DRAFT_EMAIL_TTL)
        return DraftEmailResponse(draft=draft)

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.id, a.title, a.description, a.action_payload, c.full_name AS client_name
            FROM alerts a
            JOIN clients c ON c.id = a.client_id
            WHERE a.id = %s
            """,
            (alert_id,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    title = row.get("title") or "Follow-up"
    description = row.get("description") or ""
    client_name = (row.get("client_name") or "Client").strip()
    action_payload = row.get("action_payload")
    if isinstance(action_payload, str):
        try:
            action_payload = json.loads(action_payload)
        except json.JSONDecodeError:
            action_payload = None
    model = os.environ.get("LLM_MODEL", "gpt-4o")
    draft = _call_llm_draft(client_name, title, description, action_payload, model)
    cache_set(cache_key, draft, DRAFT_EMAIL_TTL)
    return DraftEmailResponse(draft=draft)
