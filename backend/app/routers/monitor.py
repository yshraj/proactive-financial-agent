"""
Monitor / Pulse API: alerts by simulated date for the dashboard (time-travel).
GET /api/monitor/pulse?simulated_date=YYYY-MM-DD returns alerts in the next 30 days + KPI counts.
POST /api/monitor/draft-email: generate personalised email draft for an alert or meeting brief (LLM).

Every query is org-scoped twice over: an explicit ``org_id = %s`` predicate and
the RLS policies keyed on the transaction GUCs bound by app.db.get_cursor.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, date
from typing import Optional

import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

from app.context import TenantContext
from app.db import get_cursor
from app.deps import current_tenant
from app.security import limiter
from app.services.alert_helpers import (
    ALERTS_WITH_CLIENT_SQL,
    alert_from_row as _alert_row_dict,
    alert_sort_key,
    get_client_name,
    require_client_name,
    synthetic_review_overdue,
)
from app.services.cache import (
    BRIEF_TTL,
    DRAFT_EMAIL_TTL,
    PULSE_TTL,
    delete_scoped as cache_delete,
    get_scoped as cache_get,
    invalidate_client_ai_caches,
    invalidate_pulse_caches,
    set_scoped as cache_set,
)
from app.services.client_updates import validate_client_update
from app.services import audit
from app.services.analytics import compute_book_analytics
from app.services.export import rows_to_csv
from app.services.playbooks import build_playbook_alerts, list_playbooks
from app.services.llm import complete_with_system, resolve_model
from app.services.scores import (
    at_risk_score,
    next_best_actions,
    planning_completeness,
)
from app.services.prompts import (
    CLIENT_SUMMARY_SYSTEM,
    DIGEST_SYSTEM,
    DRAFT_ALERT_EMAIL_SYSTEM,
    DRAFT_BRIEF_FOLLOWUP_SYSTEM,
    PROMPT_VERSION,
    client_summary_user_message,
    digest_user_message,
    draft_alert_user_message,
    draft_brief_followup_user_message,
    review_note_user_message,
)
from app.services.prompts import REVIEW_NOTE_SYSTEM
from app.services.review_note import fallback_review_note

router = APIRouter()


class ClientOut(BaseModel):
    id: str
    full_name: str
    last_review_date: Optional[str] = None
    total_assets: Optional[float] = None
    risk_score: Optional[float] = None
    open_alert_count: int = 0


class ClientsListResponse(BaseModel):
    clients: list[ClientOut]


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


class PlanningCompleteness(BaseModel):
    score: int
    missing: list[str] = []


class AtRiskScore(BaseModel):
    score: int
    level: str
    rationale: str


class NextBestAction(BaseModel):
    action: str
    reason: str
    priority: str


class ClientDetailOut(BaseModel):
    id: str
    full_name: str
    last_review_date: Optional[str] = None
    retirement_target_age: Optional[int] = None
    risk_score: Optional[float] = None
    total_assets: Optional[float] = None
    cash_savings: Optional[float] = None
    raw_profile_json: Optional[dict] = None
    pending_alerts: list[AlertOut] = []
    overdue_follow_ups: list[AlertOut] = []
    document_count: int = 0
    summary: Optional[str] = None
    planning_completeness: Optional[PlanningCompleteness] = None
    at_risk: Optional[AtRiskScore] = None
    next_best_actions: list[NextBestAction] = []


def _alert_from_row(r: dict) -> AlertOut:
    return AlertOut(**_alert_row_dict(r))


def _document_count_for_client(cur, client_id: str, org_id: str) -> int:
    """Count documents linked to a client (org-scoped)."""
    try:
        cur.execute(
            "SELECT COUNT(*) AS n FROM ingested_documents WHERE client_id = %s AND org_id = %s",
            (client_id, org_id),
        )
        row = cur.fetchone()
        return int((row or {}).get("n") or 0)
    except psycopg2.errors.UndefinedColumn:
        return 0


@router.get("/clients", response_model=ClientsListResponse)
def get_clients(ctx: TenantContext = Depends(current_tenant)):
    """List all clients with key profile fields for dropdowns and client list page."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT c.id, c.full_name, c.last_review_date, c.total_assets, c.risk_score,
                   (SELECT COUNT(*) FROM alerts a
                    WHERE a.client_id = c.id AND a.status = 'PENDING') AS open_alert_count
            FROM clients c
            WHERE c.org_id = %s
            ORDER BY c.full_name
            """,
            (ctx.org_id,),
        )
        rows = cur.fetchall()
    clients = [
        ClientOut(
            id=str(r["id"]),
            full_name=(r.get("full_name") or "Unknown").strip(),
            last_review_date=r["last_review_date"].isoformat() if r.get("last_review_date") else None,
            total_assets=float(r["total_assets"]) if r.get("total_assets") is not None else None,
            risk_score=float(r["risk_score"]) if r.get("risk_score") is not None else None,
            open_alert_count=int(r.get("open_alert_count") or 0),
        )
        for r in rows
    ]
    return ClientsListResponse(clients=clients)


class BookAnalytics(BaseModel):
    clients_total: int
    total_aum: float
    average_risk_score: Optional[float] = None
    reviews_overdue: int


@router.get("/analytics", response_model=BookAnalytics)
def get_book_analytics(ctx: TenantContext = Depends(current_tenant)):
    """Headline metrics across the whole client book (AUM, avg risk, overdue reviews)."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT total_assets, risk_score, last_review_date FROM clients WHERE org_id = %s",
            (ctx.org_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    return BookAnalytics(**compute_book_analytics(rows, datetime.now().date()))


# CSV export column specs: (db key, human header). Kept as data so the column
# set is explicit and the serialiser stays generic.
_CLIENT_EXPORT_COLUMNS = [
    ("full_name", "Name"),
    ("last_review_date", "Last review"),
    ("total_assets", "Total assets"),
    ("cash_savings", "Cash savings"),
    ("risk_score", "Risk score"),
    ("retirement_target_age", "Retirement target age"),
    ("open_alert_count", "Open alerts"),
]
_ALERT_EXPORT_COLUMNS = [
    ("client_name", "Client"),
    ("trigger_date", "Trigger date"),
    ("type", "Type"),
    ("priority", "Priority"),
    ("status", "Status"),
    ("title", "Title"),
    ("description", "Description"),
]


def _fetch_export_rows(export_type: str, org_id: str) -> list[dict]:
    """Return plain dict rows for the requested export type (clients or alerts)."""
    with get_cursor() as cur:
        if export_type == "clients":
            cur.execute(
                """
                SELECT c.full_name, c.last_review_date, c.total_assets, c.cash_savings,
                       c.risk_score, c.retirement_target_age,
                       (SELECT COUNT(*) FROM alerts a
                        WHERE a.client_id = c.id AND a.status = 'PENDING') AS open_alert_count
                FROM clients c
                WHERE c.org_id = %s
                ORDER BY c.full_name
                """,
                (org_id,),
            )
        else:
            cur.execute(
                f"""
                {ALERTS_WITH_CLIENT_SQL}
                WHERE a.org_id = %s
                ORDER BY a.trigger_date DESC, c.full_name
                """,
                (org_id,),
            )
        rows = cur.fetchall()
    out: list[dict] = []
    for r in rows:
        row = dict(r)
        # Dates serialise as ISO strings; everything else is already CSV-safe.
        for k, v in list(row.items()):
            if hasattr(v, "isoformat"):
                row[k] = v.isoformat()
        out.append(row)
    return out


@router.get("/export")
@limiter.limit("30/minute")
def export_csv(
    request: Request,
    type: str = Query("clients", description="What to export: clients or alerts"),
    ctx: TenantContext = Depends(current_tenant),
):
    """Export the client book or alert list as a downloadable CSV file."""
    export_type = (type or "clients").strip().lower()
    if export_type not in ("clients", "alerts"):
        raise HTTPException(status_code=400, detail="type must be 'clients' or 'alerts'.")

    spec = _CLIENT_EXPORT_COLUMNS if export_type == "clients" else _ALERT_EXPORT_COLUMNS
    columns = [c for c, _ in spec]
    headers = [h for _, h in spec]
    rows = _fetch_export_rows(export_type, ctx.org_id)
    csv_text = rows_to_csv(rows, columns, headers)
    audit.record_event(
        action="data.exported",
        resource_type="export",
        resource_id=export_type,
        metadata={"rows": len(rows)},
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="kritifin-{export_type}.csv"'},
    )


class PlaybookOut(BaseModel):
    id: str
    name: str
    description: str
    task_count: int


class PlaybooksResponse(BaseModel):
    playbooks: list[PlaybookOut]


@router.get("/playbooks", response_model=PlaybooksResponse)
def get_playbooks():
    """List available task-template playbooks."""
    return PlaybooksResponse(playbooks=[PlaybookOut(**p) for p in list_playbooks()])


class ApplyPlaybookRequest(BaseModel):
    playbook_id: str


class ApplyPlaybookResponse(BaseModel):
    applied: int


@router.post("/clients/{client_id}/apply-playbook", response_model=ApplyPlaybookResponse)
@limiter.limit("30/minute")
def apply_playbook(
    request: Request,
    client_id: str,
    body: ApplyPlaybookRequest,
    ctx: TenantContext = Depends(current_tenant),
):
    """Apply a playbook to a client, creating its task templates as alerts."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT id FROM clients WHERE id = %s AND org_id = %s", (client_id, ctx.org_id)
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Client not found")
    try:
        alerts = build_playbook_alerts(body.playbook_id, datetime.now().date())
    except KeyError:
        raise HTTPException(status_code=400, detail="Unknown playbook.") from None

    rows = [
        (ctx.org_id, client_id, a["trigger_date"], a["type"], a["priority"], a["title"], a["description"])
        for a in alerts
    ]
    with get_cursor(commit=True) as cur:
        cur.executemany(
            """
            INSERT INTO alerts (org_id, client_id, trigger_date, type, priority, title, description)
            VALUES (%s, %s, %s::date, %s, %s, %s, %s)
            """,
            rows,
        )
    invalidate_client_ai_caches(client_id)
    invalidate_pulse_caches()
    audit.record_event(
        action="playbook.applied",
        resource_type="playbook",
        resource_id=body.playbook_id,
        client_id=client_id,
        metadata={"alerts_created": len(rows)},
    )
    return ApplyPlaybookResponse(applied=len(rows))


def _generate_client_summary(client_name: str, profile_bits: str, alert_lines: str, model: str) -> str:
    return complete_with_system(
        system=CLIENT_SUMMARY_SYSTEM,
        user=client_summary_user_message(
            client_name=client_name,
            profile=profile_bits,
            alerts=alert_lines,
        ),
        max_tokens=220,
        model=model,
        purpose="brief",
    )


@router.get("/clients/{client_id}", response_model=ClientDetailOut)
@limiter.limit("30/minute")
def get_client_detail(
    request: Request, client_id: str, ctx: TenantContext = Depends(current_tenant)
):
    """Client 360° view: profile, open alerts, overdue follow-ups, and AI relationship summary."""
    today = datetime.now().date()
    end_90 = today + timedelta(days=90)
    review_cutoff = today - timedelta(days=365)

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, full_name, last_review_date, retirement_target_age, risk_score,
                   total_assets, cash_savings, raw_profile_json
            FROM clients WHERE id = %s AND org_id = %s
            """,
            (client_id, ctx.org_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Client not found")

        cur.execute(
            f"""
            {ALERTS_WITH_CLIENT_SQL}
            WHERE a.client_id = %s AND a.org_id = %s AND a.status = 'PENDING'
              AND a.trigger_date >= %s AND a.trigger_date <= %s
            ORDER BY a.trigger_date, a.priority DESC
            """,
            (client_id, ctx.org_id, today, end_90),
        )
        pending_rows = cur.fetchall()

        cur.execute(
            f"""
            {ALERTS_WITH_CLIENT_SQL}
            WHERE a.client_id = %s AND a.org_id = %s AND a.trigger_date < %s
              AND a.status = 'PENDING' AND a.type = 'FOLLOW_UP'
            ORDER BY a.trigger_date ASC
            """,
            (client_id, ctx.org_id, today),
        )
        overdue_rows = cur.fetchall()

    client_name = (row.get("full_name") or "Unknown").strip()
    pending_alerts = [_alert_from_row(r) for r in pending_rows]

    last_review = row.get("last_review_date")
    if last_review is None or last_review < review_cutoff:
        pending_alerts.insert(
            0,
            AlertOut(**synthetic_review_overdue(client_id, client_name, today)),
        )

    raw_json = row.get("raw_profile_json")
    if isinstance(raw_json, str):
        try:
            raw_json = json.loads(raw_json)
        except json.JSONDecodeError:
            raw_json = None

    profile_bits = ", ".join(
        bit
        for bit in [
            f"last review {last_review}" if last_review else "no review on file",
            f"assets {row.get('total_assets')}" if row.get("total_assets") is not None else None,
            f"risk {row.get('risk_score')}" if row.get("risk_score") is not None else None,
        ]
        if bit
    )
    alert_lines = "; ".join(
        f"{a.title or a.type} (due {a.trigger_date})" for a in pending_alerts[:5]
    )

    # Separate cursor block: an UndefinedColumn would abort the transaction, so
    # isolate it from the reads above.
    with get_cursor() as cur:
        document_count = _document_count_for_client(cur, client_id, ctx.org_id)

    cache_key = f"summary:{PROMPT_VERSION}:{client_id}"
    summary = cache_get(cache_key)
    if summary is None:
        model = resolve_model("brief")
        try:
            summary = _generate_client_summary(client_name, profile_bits, alert_lines, model)
            cache_set(cache_key, summary, BRIEF_TTL)
        except Exception:
            summary = f"{client_name}: {profile_bits}. {len(pending_alerts)} open item(s)."

    overdue_follow_ups = [_alert_from_row(r) for r in overdue_rows]

    # Deterministic client-intelligence scores from the data already loaded.
    review_overdue = last_review is None or last_review < review_cutoff
    completeness = planning_completeness(
        {
            "total_assets": row.get("total_assets"),
            "cash_savings": row.get("cash_savings"),
            "risk_score": row.get("risk_score"),
            "retirement_target_age": row.get("retirement_target_age"),
            "last_review_date": last_review,
        }
    )
    high_priority = sum(1 for a in pending_alerts if a.priority == "HIGH")
    at_risk = at_risk_score(
        last_review=last_review,
        today=today,
        overdue_follow_ups=len(overdue_follow_ups),
        high_priority_alerts=high_priority,
    )
    top_pending_title = next(
        (a.title for a in pending_alerts if a.type != "REVIEW_OVERDUE" and a.title),
        None,
    )
    actions = next_best_actions(
        completeness=completeness,
        at_risk=at_risk,
        review_overdue=review_overdue,
        overdue_follow_up_titles=[a.title or "Follow-up" for a in overdue_follow_ups],
        top_pending_title=top_pending_title,
    )

    return ClientDetailOut(
        id=str(row["id"]),
        full_name=client_name,
        last_review_date=last_review.isoformat() if last_review else None,
        retirement_target_age=row.get("retirement_target_age"),
        risk_score=float(row["risk_score"]) if row.get("risk_score") is not None else None,
        total_assets=float(row["total_assets"]) if row.get("total_assets") is not None else None,
        cash_savings=float(row["cash_savings"]) if row.get("cash_savings") is not None else None,
        raw_profile_json=raw_json if isinstance(raw_json, dict) else None,
        pending_alerts=pending_alerts,
        overdue_follow_ups=overdue_follow_ups,
        document_count=document_count,
        summary=summary,
        planning_completeness=PlanningCompleteness(**completeness),
        at_risk=AtRiskScore(**at_risk),
        next_best_actions=[NextBestAction(**a) for a in actions],
    )


class ClientUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    retirement_target_age: Optional[int] = None
    risk_score: Optional[int] = None
    total_assets: Optional[float] = None
    cash_savings: Optional[float] = None
    last_review_date: Optional[str] = None


class ClientUpdateResponse(BaseModel):
    id: str
    full_name: str
    last_review_date: Optional[str] = None
    retirement_target_age: Optional[int] = None
    risk_score: Optional[float] = None
    total_assets: Optional[float] = None
    cash_savings: Optional[float] = None


@router.patch("/clients/{client_id}", response_model=ClientUpdateResponse)
@limiter.limit("60/minute")
def update_client(
    request: Request,
    client_id: str,
    body: ClientUpdateRequest,
    ctx: TenantContext = Depends(current_tenant),
):
    """Edit a client's extracted profile fields (fixes mis-extractions). Partial update."""
    try:
        # Only fields the caller explicitly set are considered, so omitted fields
        # are left untouched while an explicit null clears an optional field.
        updates = validate_client_update(body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    set_clauses = []
    params: list = []
    for col, value in updates.items():
        if col == "last_review_date":
            set_clauses.append("last_review_date = %s::date")
        else:
            set_clauses.append(f"{col} = %s")
        params.append(value)
    params.extend([client_id, ctx.org_id])

    with get_cursor(commit=True) as cur:
        cur.execute(
            "SELECT full_name, last_review_date, retirement_target_age, risk_score,"
            " total_assets, cash_savings FROM clients WHERE id = %s AND org_id = %s",
            (client_id, ctx.org_id),
        )
        before_row = cur.fetchone()
        if not before_row:
            raise HTTPException(status_code=404, detail="Client not found")
        # sql-ok: set_clauses columns come from the validate_client_update allowlist
        cur.execute(
            f"""
            UPDATE clients
            SET {', '.join(set_clauses)}, updated_at = NOW()
            WHERE id = %s AND org_id = %s
            RETURNING id, full_name, last_review_date, retirement_target_age,
                      risk_score, total_assets, cash_savings
            """,
            tuple(params),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Client not found")

    invalidate_client_ai_caches(client_id)
    audit.record_event(
        action="client.updated",
        resource_type="client",
        resource_id=client_id,
        client_id=client_id,
        before={k: before_row.get(k) for k in updates},
        after={k: row.get(k) for k in updates},
    )

    return ClientUpdateResponse(
        id=str(row["id"]),
        full_name=(row.get("full_name") or "Unknown").strip(),
        last_review_date=row["last_review_date"].isoformat() if row.get("last_review_date") else None,
        retirement_target_age=row.get("retirement_target_age"),
        risk_score=float(row["risk_score"]) if row.get("risk_score") is not None else None,
        total_assets=float(row["total_assets"]) if row.get("total_assets") is not None else None,
        cash_savings=float(row["cash_savings"]) if row.get("cash_savings") is not None else None,
    )


class ReviewNoteResponse(BaseModel):
    note: str
    generated_at: str
    ai_generated: bool


@router.post("/clients/{client_id}/review-note", response_model=ReviewNoteResponse)
@limiter.limit("30/minute")
def client_review_note(
    request: Request, client_id: str, ctx: TenantContext = Depends(current_tenant)
):
    """Generate a Consumer-Duty client review note (LLM, with deterministic fallback)."""
    today = datetime.now().date()
    review_cutoff = today - timedelta(days=365)
    end_90 = today + timedelta(days=90)

    with get_cursor() as cur:
        cur.execute(
            "SELECT id, full_name, last_review_date, total_assets, risk_score"
            " FROM clients WHERE id = %s AND org_id = %s",
            (client_id, ctx.org_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Client not found")
        cur.execute(
            f"""
            {ALERTS_WITH_CLIENT_SQL}
            WHERE a.client_id = %s AND a.org_id = %s AND a.status = 'PENDING'
              AND a.trigger_date >= %s AND a.trigger_date <= %s
            ORDER BY a.trigger_date, a.priority DESC
            """,
            (client_id, ctx.org_id, today, end_90),
        )
        pending = cur.fetchall()

    client_name = (row.get("full_name") or "Unknown").strip()
    last_review = row.get("last_review_date")
    profile_bits = ", ".join(
        bit
        for bit in [
            f"last review {last_review}" if last_review else "no review on file",
            f"assets {row.get('total_assets')}" if row.get("total_assets") is not None else None,
            f"risk {row.get('risk_score')}" if row.get("risk_score") is not None else None,
        ]
        if bit
    )
    open_items = [
        f"{(a.get('title') or a.get('type'))} (due {a['trigger_date'].isoformat() if a.get('trigger_date') else '—'})"
        for a in pending
    ]
    if last_review is None or last_review < review_cutoff:
        open_items.insert(0, "Annual review overdue")

    cache_key = f"review-note:{PROMPT_VERSION}:{client_id}"
    cached = cache_get(cache_key)
    if isinstance(cached, dict) and cached.get("note"):
        return ReviewNoteResponse(**cached)

    model = resolve_model("brief")
    try:
        note = complete_with_system(
            system=REVIEW_NOTE_SYSTEM,
            user=review_note_user_message(
                client_name=client_name,
                profile=profile_bits,
                open_items="; ".join(open_items) or "None",
            ),
            max_tokens=420,
            model=model,
            purpose="brief",
        )
        ai_generated = True
    except Exception:
        # Deterministic fallback keeps the feature working without an LLM.
        note = fallback_review_note(
            client_name=client_name,
            profile_bits=profile_bits,
            open_items=open_items,
            today_iso=today.isoformat(),
        )
        ai_generated = False

    generated_at = datetime.now().isoformat()
    payload = {"note": note, "generated_at": generated_at, "ai_generated": ai_generated}
    cache_set(cache_key, payload, BRIEF_TTL)
    audit.record(
        kind="review_note",
        client_id=client_id,
        client_name=client_name,
        model=model,
        output=note,
        ai_generated=ai_generated,
        prompt_version=PROMPT_VERSION,
    )
    return ReviewNoteResponse(**payload)


class PulseResponse(BaseModel):
    alerts: list[AlertOut]
    total: int
    high_risk: int
    deadlines: int
    client_count: int
    overdue_follow_ups: list[AlertOut] = []


class DigestResponse(BaseModel):
    digest: str
    generated_at: str


def _parse_simulated_date(simulated_date: str) -> date:
    try:
        return datetime.strptime(simulated_date, "%Y-%m-%d").date()
    except ValueError:
        return datetime.now().date()


def _build_pulse(base: date, org_id: str) -> PulseResponse:
    """Shared pulse logic for dashboard and morning digest."""
    end = base + timedelta(days=30)
    review_cutoff = base - timedelta(days=365)

    with get_cursor() as cur:
        cur.execute(
            f"""
            {ALERTS_WITH_CLIENT_SQL}
            WHERE a.org_id = %s AND a.trigger_date >= %s AND a.trigger_date <= %s
              AND a.status = 'PENDING'
            ORDER BY a.trigger_date, a.priority DESC
            """,
            (org_id, base, end),
        )
        rows = cur.fetchall()

        cur.execute(
            """
            SELECT c.id AS client_id, c.full_name AS client_name, c.last_review_date
            FROM clients c
            WHERE c.org_id = %s AND (c.last_review_date IS NULL OR c.last_review_date < %s)
            ORDER BY c.last_review_date NULLS FIRST
            """,
            (org_id, review_cutoff),
        )
        review_overdue_rows = cur.fetchall()

        cur.execute("SELECT COUNT(*) AS n FROM clients WHERE org_id = %s", (org_id,))
        client_count = cur.fetchone()["n"] or 0

        cur.execute(
            f"""
            {ALERTS_WITH_CLIENT_SQL}
            WHERE a.org_id = %s AND a.trigger_date < %s AND a.status = 'PENDING'
              AND a.type = 'FOLLOW_UP'
            ORDER BY a.trigger_date ASC
            """,
            (org_id, base),
        )
        overdue_follow_up_rows = cur.fetchall()

    alerts = [_alert_from_row(r) for r in rows]

    for r in review_overdue_rows:
        cid = str(r["client_id"])
        alerts.append(
            AlertOut(**synthetic_review_overdue(cid, r["client_name"] or "Unknown", base))
        )

    alerts.sort(key=alert_sort_key)

    return PulseResponse(
        alerts=alerts,
        total=len(alerts),
        high_risk=sum(1 for a in alerts if a.priority == "HIGH"),
        deadlines=sum(1 for a in alerts if a.type == "DEADLINE"),
        client_count=client_count,
        overdue_follow_ups=[_alert_from_row(r) for r in overdue_follow_up_rows],
    )


def _get_pulse_cached(simulated_date: str, org_id: str) -> PulseResponse:
    """Return pulse data, reusing a short-lived cache shared with /digest."""
    cache_key = f"pulse:{simulated_date}"
    cached = cache_get(cache_key)
    if isinstance(cached, dict):
        return PulseResponse.model_validate(cached)
    base = _parse_simulated_date(simulated_date)
    pulse = _build_pulse(base, org_id)
    cache_set(cache_key, pulse.model_dump(), PULSE_TTL)
    return pulse


def _generate_morning_digest(pulse: PulseResponse, simulated_date: str, model: str) -> str:
    priority_lines = [
        f"- {a.client_name}: {a.title or a.type} (due {a.trigger_date}, {a.priority} priority)"
        for a in pulse.alerts[:7]
    ]
    follow_up_lines = [
        f"- {a.client_name}: {a.title or 'Follow-up'} (was due {a.trigger_date})"
        for a in pulse.overdue_follow_ups[:5]
    ]
    context = f"""Date: {simulated_date}
Open priorities: {pulse.total} | High priority: {pulse.high_risk} | Deadlines: {pulse.deadlines} | Clients: {pulse.client_count}

Top priorities:
{chr(10).join(priority_lines) or 'None'}

Overdue follow-ups:
{chr(10).join(follow_up_lines) or 'None'}"""

    return complete_with_system(
        system=DIGEST_SYSTEM,
        user=digest_user_message(context=context),
        max_tokens=280,
        model=model,
        purpose="brief",
    )


@router.get("/pulse", response_model=PulseResponse)
def get_pulse(
    simulated_date: str = Query(..., description="YYYY-MM-DD"),
    ctx: TenantContext = Depends(current_tenant),
):
    """
    Alerts whose trigger_date is in [simulated_date, simulated_date + 30 days], status PENDING.
    Joins clients for display name. Also returns KPI counts for the dashboard.
    """
    return _get_pulse_cached(simulated_date, ctx.org_id)


@router.get("/digest", response_model=DigestResponse)
@limiter.limit("30/minute")
def get_digest(
    request: Request,
    simulated_date: str = Query(..., description="YYYY-MM-DD"),
    refresh: bool = Query(False, description="Bypass cache and regenerate digest"),
    ctx: TenantContext = Depends(current_tenant),
):
    """AI-generated morning briefing summarising today's priorities from pulse data."""
    if refresh:
        invalidate_pulse_caches()
    pulse = _get_pulse_cached(simulated_date, ctx.org_id)
    pulse_json = pulse.model_dump_json()
    ctx_hash = hashlib.md5(pulse_json.encode()).hexdigest()[:16]
    cache_key = f"digest:{PROMPT_VERSION}:{simulated_date}:{ctx_hash}"

    if not refresh:
        cached = cache_get(cache_key)
        if isinstance(cached, dict) and cached.get("digest"):
            return DigestResponse(
                digest=cached["digest"],
                generated_at=cached.get("generated_at", datetime.now().isoformat()),
            )

    model = resolve_model("brief")
    ai_generated = True
    try:
        digest_text = _generate_morning_digest(pulse, simulated_date, model)
    except Exception:
        ai_generated = False
        if pulse.total == 0:
            digest_text = "Your book looks clear today — a good moment for proactive client outreach or reviewing uploaded documents."
        else:
            top = pulse.alerts[0]
            digest_text = (
                f"You have {pulse.total} open priorities. Start with {top.client_name}: "
                f"{top.title or top.type} due {top.trigger_date}."
            )

    generated_at = datetime.now().isoformat()
    cache_set(cache_key, {"digest": digest_text, "generated_at": generated_at}, BRIEF_TTL)
    audit.record(kind="digest", model=model, output=digest_text,
                 ai_generated=ai_generated, prompt_version=PROMPT_VERSION)
    return DigestResponse(digest=digest_text, generated_at=generated_at)


class AlertsListResponse(BaseModel):
    alerts: list[AlertOut]


@router.get("/alerts", response_model=AlertsListResponse)
def get_alerts(
    simulated_date: Optional[str] = Query(None, description="YYYY-MM-DD (default: today)"),
    days: int = Query(90, ge=1, le=730, description="Window: simulated_date to +days"),
    type_filter: Optional[str] = Query(None, alias="type", description="Filter by type"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: PENDING, COMPLETED, or omit for all"),
    ctx: TenantContext = Depends(current_tenant),
):
    """
    All alerts in [simulated_date, simulated_date + days], with optional type/priority/status filters.
    Includes synthetic REVIEW_OVERDUE for clients with no review in 12+ months (PENDING only).
    """
    base = _parse_simulated_date(simulated_date) if simulated_date else datetime.now().date()
    end = base + timedelta(days=days)
    review_cutoff = base - timedelta(days=365)

    with get_cursor() as cur:
        sql = f"""
            {ALERTS_WITH_CLIENT_SQL}
            WHERE a.org_id = %s AND a.trigger_date >= %s AND a.trigger_date <= %s
            """
        params: list = [ctx.org_id, base, end]
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
            WHERE c.org_id = %s AND (c.last_review_date IS NULL OR c.last_review_date < %s)
            """,
            (ctx.org_id, review_cutoff),
        )
        review_overdue_rows = cur.fetchall()

    alerts = [_alert_from_row(r) for r in rows]

    for r in review_overdue_rows:
        cid = str(r["client_id"])
        if status_filter and status_filter.upper() == "COMPLETED":
            continue
        if type_filter and type_filter != "REVIEW_OVERDUE":
            continue
        if priority and priority != "HIGH":
            continue
        alerts.append(
            AlertOut(**synthetic_review_overdue(cid, r["client_name"] or "Unknown", base))
        )

    alerts.sort(key=alert_sort_key)

    return AlertsListResponse(alerts=alerts)


@router.get("/completed", response_model=AlertsListResponse)
def get_completed(
    limit: int = Query(10, ge=1, le=50, description="Max number of recently completed alerts"),
    ctx: TenantContext = Depends(current_tenant),
):
    """
    Recently completed (marked as done) alerts, ordered by updated_at descending.
    For display on the dashboard without Draft Email option.
    """
    with get_cursor() as cur:
        cur.execute(
            f"""
            {ALERTS_WITH_CLIENT_SQL}
            WHERE a.org_id = %s AND a.status = 'COMPLETED'
            ORDER BY a.updated_at DESC
            LIMIT %s
            """,
            (ctx.org_id, limit),
        )
        rows = cur.fetchall()
    alerts = [_alert_from_row(r) for r in rows]
    return AlertsListResponse(alerts=alerts)


class AlertStatusUpdate(BaseModel):
    status: str  # e.g. 'COMPLETED'


@router.patch("/alerts/{alert_id}/status", response_model=AlertOut)
@limiter.limit("60/minute")
def update_alert_status(
    alert_id: str,
    body: AlertStatusUpdate,
    request: Request,
    ctx: TenantContext = Depends(current_tenant),
):
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
            """
            UPDATE alerts a
            SET status = %s, updated_at = NOW()
            FROM clients c
            WHERE a.id = %s AND a.org_id = %s AND c.id = a.client_id
            RETURNING a.id, a.client_id, a.trigger_date, a.type, a.priority,
                      a.title, a.description, a.status, c.full_name AS client_name
            """,
            (status, alert_id, ctx.org_id),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    cache_delete(f"draft:{PROMPT_VERSION}:{alert_id}")
    invalidate_client_ai_caches(str(row["client_id"]))
    audit.record_event(
        action="alert.status_changed",
        resource_type="alert",
        resource_id=alert_id,
        client_id=str(row["client_id"]),
        after={"status": status},
    )
    return AlertOut(
        id=str(row["id"]),
        client_id=str(row["client_id"]),
        client_name=row["client_name"] or "Unknown",
        trigger_date=row["trigger_date"].isoformat() if row["trigger_date"] else "",
        type=(row["type"] or ""),
        priority=(row["priority"] or ""),
        title=row["title"],
        description=row["description"],
        status=(row["status"] or status),
    )


class DraftEmailRequest(BaseModel):
    alert_id: Optional[str] = None
    client_id: Optional[str] = None
    context: Optional[str] = None
    talking_points: Optional[list[str]] = None


class DraftEmailResponse(BaseModel):
    draft: str
    subject: Optional[str] = None


def _call_llm_draft(client_name: str, title: str, description: str, action_payload: Optional[dict], model: str) -> str:
    payload_str = json.dumps(action_payload, indent=2) if action_payload else "None"
    return complete_with_system(
        system=DRAFT_ALERT_EMAIL_SYSTEM,
        user=draft_alert_user_message(
            client_name=client_name,
            title=title or "Follow-up",
            description=description or "No description.",
            action_payload=payload_str,
        ),
        max_tokens=450,
        model=model,
        purpose="draft",
    )


def _call_llm_brief_followup(
    client_name: str,
    context: str,
    talking_points: Optional[list[str]],
    model: str,
) -> str:
    points_str = "\n".join(f"- {p}" for p in (talking_points or [])) if talking_points else "None listed"
    return complete_with_system(
        system=DRAFT_BRIEF_FOLLOWUP_SYSTEM,
        user=draft_brief_followup_user_message(
            client_name=client_name,
            context=(context or "")[:3000],
            talking_points=points_str,
        ),
        max_tokens=450,
        model=model,
        purpose="draft",
    )


@router.post("/draft-email", response_model=DraftEmailResponse)
@limiter.limit("30/minute")
def draft_email(
    request: Request, body: DraftEmailRequest, ctx: TenantContext = Depends(current_tenant)
):
    """Generate a personalised email draft for an alert or meeting brief. Cached by alert_id or client+context hash."""
    model = resolve_model("draft")

    if body.client_id and (body.context or "").strip():
        client_id = body.client_id.strip()
        context = (body.context or "").strip()
        ctx_hash = hashlib.md5(context.encode()).hexdigest()[:16]
        cache_key = f"draft:{PROMPT_VERSION}:brief:{client_id}:{ctx_hash}"
        draft = cache_get(cache_key)
        if draft is not None:
            return DraftEmailResponse(
                draft=draft,
                subject=f"Follow-up: {get_client_name(client_id)}",
            )
        try:
            client_name = require_client_name(client_id)
        except LookupError:
            raise HTTPException(status_code=404, detail="Client not found") from None
        draft = _call_llm_brief_followup(client_name, context, body.talking_points, model)
        cache_set(cache_key, draft, DRAFT_EMAIL_TTL)
        audit.record(kind="draft_email", client_id=client_id, client_name=client_name,
                     model=model, output=draft, prompt_version=PROMPT_VERSION)
        return DraftEmailResponse(draft=draft, subject=f"Follow-up: {client_name}")

    alert_id = (body.alert_id or "").strip()
    if not alert_id:
        raise HTTPException(
            status_code=400,
            detail="Provide alert_id or client_id with context for brief follow-up.",
        )

    cache_key = f"draft:{PROMPT_VERSION}:{alert_id}"
    draft = cache_get(cache_key)
    if draft is not None:
        return DraftEmailResponse(draft=draft)

    if alert_id.startswith("review-overdue-"):
        client_id = alert_id.replace("review-overdue-", "", 1)
        try:
            client_name = require_client_name(client_id)
        except LookupError:
            raise HTTPException(status_code=404, detail="Client not found") from None
        title = "Annual review overdue"
        description = "No review in 12+ months. Consumer Duty requires demonstrating ongoing value."
        draft = _call_llm_draft(client_name, title, description, None, model)
        cache_set(cache_key, draft, DRAFT_EMAIL_TTL)
        audit.record(kind="draft_email", client_id=client_id, client_name=client_name,
                     model=model, output=draft, prompt_version=PROMPT_VERSION)
        return DraftEmailResponse(draft=draft)

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.id, a.client_id, a.title, a.description, a.action_payload,
                   c.full_name AS client_name
            FROM alerts a
            JOIN clients c ON c.id = a.client_id
            WHERE a.id = %s AND a.org_id = %s
            """,
            (alert_id, ctx.org_id),
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
    draft = _call_llm_draft(client_name, title, description, action_payload, model)
    cache_set(cache_key, draft, DRAFT_EMAIL_TTL)
    audit.record(kind="draft_email",
                 client_id=str(row["client_id"]) if row.get("client_id") else None,
                 client_name=client_name, model=model, output=draft,
                 prompt_version=PROMPT_VERSION)
    return DraftEmailResponse(draft=draft)
