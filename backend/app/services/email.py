"""SMTP email sending for the public contact form.

Zoho Mail is the default provider (see .env.example), but any SMTP-over-SSL
(implicit TLS, typically port 465) provider works — only the env var names
are Zoho-flavored. Sending is synchronous/blocking (stdlib smtplib); callers
on the async request path must wrap calls in
``starlette.concurrency.run_in_threadpool``.
"""
from __future__ import annotations

import logging
import os
import re
import smtplib
from email.message import EmailMessage

logger = logging.getLogger("jarvis.email")

_SEND_TIMEOUT_SECONDS = 10
# Defense in depth against header injection: header-bound fields (name,
# email, topic) are stripped of CR/LF before ever reaching an EmailMessage
# header, regardless of how well the stdlib email package already escapes them.
_HEADER_INJECTION_RE = re.compile(r"[\r\n]+")


class EmailNotConfigured(Exception):
    """SMTP env vars are incomplete; the contact form is disabled."""


class EmailSendError(Exception):
    """The SMTP send itself failed (auth, network, provider rejection, ...)."""


def _clean_header_value(value: str) -> str:
    return _HEADER_INJECTION_RE.sub(" ", value).strip()


def _smtp_config() -> dict[str, str] | None:
    host = os.environ.get("ZOHO_SMTP_HOST", "").strip()
    port = os.environ.get("ZOHO_SMTP_PORT", "").strip()
    user = os.environ.get("ZOHO_SMTP_USER", "").strip()
    password = os.environ.get("ZOHO_SMTP_PASS", "").strip()
    to_email = os.environ.get("CONTACT_TO_EMAIL", "").strip()
    from_email = os.environ.get("CONTACT_FROM_EMAIL", "").strip() or user
    if not (host and port and user and password and to_email and from_email):
        return None
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "to_email": to_email,
        "from_email": from_email,
    }


def contact_form_configured() -> bool:
    """Whether the backend can actually send a contact-form email right now."""
    if os.environ.get("CONTACT_ENABLED", "true").strip().lower() not in ("1", "true", "yes"):
        return False
    return _smtp_config() is not None


def send_contact_email(*, name: str, email: str, topic: str, message: str) -> None:
    """Send one contact-form submission to the support inbox.

    Blocking network I/O — see module docstring on threading this from async
    routes. Raises :class:`EmailNotConfigured` / :class:`EmailSendError`;
    callers translate these to client-safe HTTP responses (never surface
    ``str(exc)`` — SMTP errors can carry hostnames/credentials in their text).
    """
    config = _smtp_config()
    if config is None:
        raise EmailNotConfigured("Contact form SMTP is not configured.")

    safe_name = _clean_header_value(name)
    safe_email = _clean_header_value(email)
    safe_topic = _clean_header_value(topic)

    msg = EmailMessage()
    msg["Subject"] = f"[KritiFin Contact] {safe_topic} — {safe_name}"
    msg["From"] = config["from_email"]
    msg["To"] = config["to_email"]
    # Lets support hit "reply" and land straight in the visitor's inbox.
    msg["Reply-To"] = safe_email
    msg.set_content(
        "New contact form submission\n\n"
        f"Name: {safe_name}\n"
        f"Email: {safe_email}\n"
        f"Topic: {safe_topic}\n\n"
        f"Message:\n{message}\n"
    )

    try:
        with smtplib.SMTP_SSL(
            config["host"], int(config["port"]), timeout=_SEND_TIMEOUT_SECONDS
        ) as server:
            server.login(config["user"], config["password"])
            server.send_message(msg)
    except Exception as exc:  # noqa: BLE001 - SMTP failures must not leak details to the client
        logger.exception("Contact form email send failed")
        raise EmailSendError("Failed to send contact email.") from exc
