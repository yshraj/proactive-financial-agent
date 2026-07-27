"""
Centralized logging configuration.

Emits one JSON object per line (set LOG_FORMAT=text for the human-readable
dev format) with request/tenant correlation pulled from app.context, so every
log line produced while serving a request carries its request_id / org_id /
user_id without call sites doing anything.

PII policy: never log client names, document text, or generated output at
INFO+; the scrubber below additionally masks values for obviously sensitive
key names when structured `extra` fields are used.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

_SENSITIVE_KEY_FRAGMENTS = ("password", "secret", "token", "api_key", "authorization")

_STDLIB_RECORD_FIELDS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "message", "asctime",
}


def _scrub(key: str, value: object) -> object:
    lowered = key.lower()
    if any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS):
        return "[redacted]"
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        from app.context import get_current_tenant, get_request_id

        payload: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        request_id = get_request_id()
        if request_id:
            payload["request_id"] = request_id
        tenant = get_current_tenant()
        if tenant is not None:
            payload["org_id"] = tenant.org_id or None
            if tenant.user_id:
                payload["user_id"] = tenant.user_id
        for key, value in record.__dict__.items():
            if key in _STDLIB_RECORD_FIELDS or key.startswith("_") or key in payload:
                continue
            payload[key] = _scrub(key, value)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    """Dev-friendly single-line format, still with request correlation."""

    def format(self, record: logging.LogRecord) -> str:
        from app.context import get_request_id

        request_id = get_request_id()
        record.rid = f" rid={request_id}" if request_id else ""
        return super().format(record)


def configure_logging(*, force: bool = False) -> None:
    """Install the JSON/text formatter on the root logger.

    ``force=True`` replaces any pre-installed root handlers with our own
    stream handler instead of just re-formatting them. The worker Lambda
    needs this: awslambdaric pre-installs a root handler whose sink buffers
    records — in production its output surfaced in CloudWatch hours late, as
    multi-record chunks glued into one event (useless during an incident).
    A plain per-record-flushing StreamHandler shows up in CloudWatch live,
    exactly like the API function's logs.
    """
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    use_json = (os.environ.get("LOG_FORMAT", "json").lower() != "text")

    formatter: logging.Formatter
    if use_json:
        formatter = JsonFormatter()
    else:
        formatter = TextFormatter("%(asctime)s %(levelname)s [%(name)s]%(rid)s %(message)s")

    root = logging.getLogger()
    if root.handlers and not force:
        # Already configured (e.g. uvicorn reload) — reset formatter + level.
        for handler in root.handlers:
            handler.setFormatter(formatter)
        root.setLevel(level)
    else:
        for stale in list(root.handlers):
            root.removeHandler(stale)
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root.addHandler(handler)
        root.setLevel(level)

    # Quiet noisy third-party loggers a touch.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
