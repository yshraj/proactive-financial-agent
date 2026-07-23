"""Shared OpenAI completion helpers."""
from __future__ import annotations

import os
from typing import Literal, Optional

Purpose = Literal["brief", "chat", "draft"]

# Low temperature for consistent, factual adviser outputs
DEFAULT_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0"))


class AIUnavailableError(RuntimeError):
    """LLM provider call failed (outage, timeout, quota).

    Carries only the fixed public message — the provider's error text is
    logged by public_error_message, never surfaced. Endpoints that don't
    catch it get a clean 503 from the handler in app.main; features with
    deterministic fallbacks (digest, review note) catch Exception and keep
    their fallback behaviour.
    """


def resolve_model(purpose: Purpose = "chat") -> str:
    if purpose == "brief":
        return os.environ.get("BRIEF_LLM_MODEL") or os.environ.get("LLM_MODEL") or "gpt-4o-mini"
    if purpose == "draft":
        return os.environ.get("DRAFT_LLM_MODEL") or os.environ.get("BRIEF_LLM_MODEL") or os.environ.get("LLM_MODEL") or "gpt-4o-mini"
    return os.environ.get("LLM_MODEL", "gpt-4o")


def complete(
    *,
    messages: list[dict[str, str]],
    max_tokens: int,
    model: Optional[str] = None,
    purpose: Purpose = "chat",
    temperature: Optional[float] = None,
) -> str:
    from app.services.clients import get_openai_client
    from app.services.llm_usage import record_usage
    from app.services.safety import public_error_message

    client = get_openai_client()
    resolved_model = model or resolve_model(purpose)
    try:
        response = client.chat.completions.create(
            model=resolved_model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=DEFAULT_TEMPERATURE if temperature is None else temperature,
        )
    except Exception as exc:
        # Full provider error goes to the logs; clients get fixed copy only.
        raise AIUnavailableError(public_error_message("ai_unavailable", exc)) from exc
    record_usage(model=resolved_model, purpose=purpose, usage=getattr(response, "usage", None))
    return (response.choices[0].message.content or "").strip()


def complete_with_system(
    *,
    system: str,
    user: str,
    max_tokens: int,
    purpose: Purpose = "chat",
    model: Optional[str] = None,
) -> str:
    return complete(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        model=model,
        purpose=purpose,
    )
