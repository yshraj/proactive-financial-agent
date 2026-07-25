"""Public "Contact us / report an issue" submissions -> support inbox.

Deliberately unauthenticated (mounted without the usual api_guard): logged-out
marketing-site visitors need it as much as signed-in users reporting a bug, and
requiring the shared access code or a Supabase session would block exactly the
prospects it exists to capture. The trade-off is covered by a tight per-minute
rate limit (keyed per browser session / IP, see app.security) and a honeypot
field instead of tenant auth.
"""
from __future__ import annotations

import logging
import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.security import limiter
from app.services.email import EmailNotConfigured, EmailSendError, send_contact_email

logger = logging.getLogger("jarvis.contact")

router = APIRouter()

_UNAVAILABLE_MESSAGE = "Contact form is temporarily unavailable. Please try again later."
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

Topic = Literal["general", "support", "bug", "sales"]


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    topic: Topic = "general"
    message: str = Field(min_length=10, max_length=4000)
    # Hidden via CSS on the frontend; a filled value means a bot, not a visitor.
    website: str = Field(default="", max_length=200)


class ContactOut(BaseModel):
    ok: bool = True


@router.post("", response_model=ContactOut, status_code=202)
@router.post("/", response_model=ContactOut, status_code=202, include_in_schema=False)
@limiter.limit("5/minute")
async def submit_contact(request: Request, response: Response, body: ContactIn):
    if body.website.strip():
        # Honeypot tripped: report success so the bot doesn't learn anything,
        # but drop the submission on the floor.
        logger.info("Contact form honeypot tripped; dropping submission.")
        return ContactOut()

    name = body.name.strip()
    email = body.email.strip()
    message = body.message.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Please enter your name.")
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Please enter a valid email address.")
    if len(message) < 10:
        raise HTTPException(
            status_code=422, detail="Please add a bit more detail to your message."
        )

    try:
        await run_in_threadpool(
            send_contact_email, name=name, email=email, topic=body.topic, message=message
        )
    except EmailNotConfigured:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE_MESSAGE) from None
    except EmailSendError:
        raise HTTPException(
            status_code=502,
            detail="We couldn't send your message. Please try again shortly.",
        ) from None

    return ContactOut()
