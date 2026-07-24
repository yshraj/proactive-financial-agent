"""Shared LLM completion helpers (facade over the multi-provider gateway).

Callers keep the same tiny surface they always had — ``complete`` /
``complete_with_system`` returning a string — while routing, quota
management, fallbacks, and usage accounting live in
``services.model_gateway``. The ``*_ex`` variants additionally return the
:class:`~app.services.model_gateway.GatewayResult` so audit trails can
record which provider/model actually answered.
"""
from __future__ import annotations

import os
from typing import Literal, Optional

from app.services.model_gateway import GatewayResult, GatewayUnavailableError

Purpose = Literal["brief", "chat", "draft", "extraction", "agent", "reviewer", "fast"]

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


def resolve_model(purpose: Purpose = "chat") -> Optional[str]:
    """Optional env-pinned model for this purpose (None = route by purpose).

    Kept for backwards compatibility with the pre-gateway configuration:
    LLM_MODEL / BRIEF_LLM_MODEL / DRAFT_LLM_MODEL pin a specific model, which
    the gateway tries first (falling back down the purpose chain). Unset —
    the default — lets the quota-aware router pick the best free option.
    """
    if purpose == "brief":
        return os.environ.get("BRIEF_LLM_MODEL") or os.environ.get("LLM_MODEL") or None
    if purpose == "draft":
        return (
            os.environ.get("DRAFT_LLM_MODEL")
            or os.environ.get("BRIEF_LLM_MODEL")
            or os.environ.get("LLM_MODEL")
            or None
        )
    return os.environ.get("LLM_MODEL") or None


def complete_ex(
    *,
    messages: list[dict[str, str]],
    max_tokens: int,
    model: Optional[str] = None,
    purpose: Purpose = "chat",
    temperature: Optional[float] = None,
    response_format: Optional[dict] = None,
) -> GatewayResult:
    """Run a completion and return the full gateway result (content + which
    provider/model answered + token usage)."""
    from app.services import model_gateway
    from app.services.safety import public_error_message

    try:
        return model_gateway.chat(
            messages=messages,
            purpose=purpose,
            max_tokens=max_tokens,
            temperature=DEFAULT_TEMPERATURE if temperature is None else temperature,
            model=model or resolve_model(purpose),
            response_format=response_format,
        )
    except GatewayUnavailableError as exc:
        # Full provider detail goes to the logs; clients get fixed copy only.
        raise AIUnavailableError(public_error_message("ai_unavailable", exc)) from exc
    except Exception as exc:
        raise AIUnavailableError(public_error_message("ai_unavailable", exc)) from exc


def complete(
    *,
    messages: list[dict[str, str]],
    max_tokens: int,
    model: Optional[str] = None,
    purpose: Purpose = "chat",
    temperature: Optional[float] = None,
    response_format: Optional[dict] = None,
) -> str:
    return complete_ex(
        messages=messages,
        max_tokens=max_tokens,
        model=model,
        purpose=purpose,
        temperature=temperature,
        response_format=response_format,
    ).content


def complete_with_system_ex(
    *,
    system: str,
    user: str,
    max_tokens: int,
    purpose: Purpose = "chat",
    model: Optional[str] = None,
    response_format: Optional[dict] = None,
) -> GatewayResult:
    return complete_ex(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        model=model,
        purpose=purpose,
        response_format=response_format,
    )


def complete_with_system(
    *,
    system: str,
    user: str,
    max_tokens: int,
    purpose: Purpose = "chat",
    model: Optional[str] = None,
) -> str:
    return complete_with_system_ex(
        system=system,
        user=user,
        max_tokens=max_tokens,
        purpose=purpose,
        model=model,
    ).content
