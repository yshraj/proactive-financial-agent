"""
Centralized logging configuration.

Emits structured-ish single-line logs with level, logger name, and a request id
where available. Keeps the existing "jarvis.ingest" channel working.
"""
import logging
import os


def configure_logging() -> None:
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    if root.handlers:
        # Already configured (e.g. uvicorn reload) — just set level.
        root.setLevel(level)
        return

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(level)

    # Quiet noisy third-party loggers a touch.
    logging.getLogger("httpx").setLevel(logging.WARNING)
