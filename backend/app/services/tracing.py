"""
Optional LLM observability via Langfuse (Cloud Hobby free tier).

Env-gated and fail-open: without LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY
every function here is a no-op, and no tracing error can ever break a
request or an agent run.

What gets traced:
- every gateway completion (provider, model, purpose, latency, token usage)
  via the generation hook registered by :func:`install`;
- every agent run as a trace (id = run id), with one span per recorded
  step (plan, each tool call, synthesis, review) — mirroring the
  ``agent_steps`` timeline users see in the app.

Content policy: prompts/outputs are sent to Langfuse for debugging value
(that is the point of tracing) unless ``LANGFUSE_MASK_CONTENT=true``, in
which case only lengths and metadata are recorded. The demo workspace runs
on mock data; masked mode is the setting for real client books.

Lambda note: the SDK batches in a background thread which freezes between
invocations, so the worker flushes after each queue drain and the API
flushes at shutdown; stragglers ride along with the next invocation.
"""
from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from typing import Any, Optional

logger = logging.getLogger("jarvis.tracing")

_client_instance = None
_client_failed = False
_installed = False

# The active run trace (worker-side); gateway generations attach to it.
_current_trace_id: "ContextVar[Optional[str]]" = ContextVar("langfuse_trace_id", default=None)


def enabled() -> bool:
    return bool(
        (os.environ.get("LANGFUSE_PUBLIC_KEY") or "").strip()
        and (os.environ.get("LANGFUSE_SECRET_KEY") or "").strip()
    )


def _mask() -> bool:
    return (os.environ.get("LANGFUSE_MASK_CONTENT") or "").strip().lower() in ("1", "true", "yes")


def _client():
    """Lazy Langfuse client; None when unconfigured or the SDK failed."""
    global _client_instance, _client_failed
    if not enabled() or _client_failed:
        return None
    if _client_instance is None:
        try:
            from langfuse import Langfuse

            _client_instance = Langfuse(
                public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
                secret_key=os.environ["LANGFUSE_SECRET_KEY"],
                host=os.environ.get("LANGFUSE_HOST") or "https://cloud.langfuse.com",
            )
        except Exception:  # noqa: BLE001 - observability must never break the app
            logger.exception("Langfuse client init failed; tracing disabled")
            _client_failed = True
            return None
    return _client_instance


def _content(value: Any, cap: int = 4000) -> Any:
    """Apply the content policy to a prompt/output value."""
    if _mask():
        if isinstance(value, str):
            return f"<masked: {len(value)} chars>"
        if isinstance(value, list):
            return f"<masked: {len(value)} messages>"
        return "<masked>"
    if isinstance(value, str):
        return value[:cap]
    if isinstance(value, list):
        return [
            {**m, "content": str(m.get("content") or "")[:cap]} if isinstance(m, dict) else m
            for m in value
        ]
    return value


def install() -> None:
    """Register the gateway generation hook (idempotent, cheap when disabled)."""
    global _installed
    if _installed:
        return
    from app.services import model_gateway

    model_gateway.add_generation_hook(_on_generation)
    _installed = True


def _on_generation(*, spec, purpose, messages, result, error) -> None:
    client = _client()
    if client is None:
        return
    try:
        usage = None
        if result is not None and result.usage:
            usage = {
                "input": int(result.usage.get("prompt_tokens") or 0),
                "output": int(result.usage.get("completion_tokens") or 0),
            }
        client.generation(
            trace_id=_current_trace_id.get(),
            name=f"llm:{purpose}",
            model=(result.label if result is not None else (spec.label if spec else "unrouted")),
            input=_content(messages),
            output=_content(result.content) if result is not None else None,
            usage=usage,
            metadata={
                "purpose": purpose,
                "provider": result.provider if result is not None else None,
                "latency_ms": result.latency_ms if result is not None else None,
                "error": (error or "")[:500] or None,
            },
            level="ERROR" if error else "DEFAULT",
        )
    except Exception:  # noqa: BLE001
        logger.exception("Langfuse generation event failed")


def start_run_trace(*, run_id: str, kind: str, org_id: str, query: str = "") -> None:
    """Open a trace for one agent run; gateway generations nest under it."""
    client = _client()
    if client is None:
        return
    try:
        client.trace(
            id=run_id,
            name=f"agent:{kind}",
            input=_content(query),
            metadata={"org_id": org_id, "kind": kind},
            tags=["agent-run", kind],
        )
        _current_trace_id.set(run_id)
    except Exception:  # noqa: BLE001
        logger.exception("Langfuse trace start failed")


def record_step(
    *,
    node: str,
    label: str,
    status: str,
    detail: Optional[dict] = None,
) -> None:
    """One span per finished agent step (mirrors the agent_steps timeline)."""
    client = _client()
    trace_id = _current_trace_id.get()
    if client is None or trace_id is None:
        return
    try:
        client.span(
            trace_id=trace_id,
            name=node,
            output=_content(str(detail)) if detail else None,
            metadata={"label": label, "status": status},
            level="ERROR" if status == "ERROR" else "DEFAULT",
        )
    except Exception:  # noqa: BLE001
        logger.exception("Langfuse step span failed")


def end_run_trace(*, output: Optional[dict] = None, error: Optional[str] = None) -> None:
    client = _client()
    trace_id = _current_trace_id.get()
    _current_trace_id.set(None)
    if client is None or trace_id is None:
        return
    try:
        client.trace(
            id=trace_id,
            output=_content(str(output)) if output else None,
            metadata={"error": error} if error else None,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Langfuse trace end failed")


def flush() -> None:
    """Drain the SDK's event buffer (worker: after each drain; API: shutdown)."""
    client = _client()
    if client is None:
        return
    try:
        client.flush()
    except Exception:  # noqa: BLE001
        logger.exception("Langfuse flush failed")


def reset_for_tests() -> None:
    global _client_instance, _client_failed, _installed
    _client_instance = None
    _client_failed = False
    _installed = False
    _current_trace_id.set(None)
