"""
LLM token-usage accounting: one structured log line per OpenAI call.

Every completion/embedding call emits an ``llm_usage`` event with token
counts and a rough cost estimate. CloudWatch metric filters in
deploy/aws/template.yaml turn these into KritiFin/LlmTokens and
KritiFin/LlmEstCostUsd — the day-one signals for "what does each feature
cost" and "when does OpenAI spend need attention". Log-only otherwise:
no database writes, no external calls.

Prices are indicative (USD per 1M tokens) and exist to make the metric
directionally useful, not to be an invoice — reconcile real spend in the
OpenAI dashboard. Unknown models log tokens with cost 0.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("jarvis.llm_usage")

# (input, output) USD per 1M tokens. Update when models/prices change.
_PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "text-embedding-3-small": (0.02, 0.0),
}


def _estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    # Match on prefix so dated snapshots (gpt-4o-2024-...) price like the base
    # model; check longer keys first so gpt-4o-mini doesn't match gpt-4o.
    for key in sorted(_PRICES_PER_MTOK, key=len, reverse=True):
        if model.startswith(key):
            input_price, output_price = _PRICES_PER_MTOK[key]
            return round(
                (prompt_tokens * input_price + completion_tokens * output_price) / 1e6,
                6,
            )
    return 0.0


def record_usage(*, model: str, purpose: str, usage: Optional[Any]) -> None:
    """Log one llm_usage event from an OpenAI response's ``.usage`` object.

    ``usage`` may be None (the API can omit it); nothing is logged then.
    Never raises — accounting must not break the call it measures.
    """
    if usage is None:
        return
    try:
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(
            getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens)
        )
        logger.info(
            "llm_usage model=%s purpose=%s total_tokens=%d",
            model, purpose, total_tokens,
            extra={
                "event": "llm_usage",
                "model": model,
                "purpose": purpose,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "est_cost_usd": _estimate_cost_usd(
                    model, prompt_tokens, completion_tokens
                ),
            },
        )
    except Exception:  # noqa: BLE001 - accounting must never break the caller
        logger.exception("Failed to record LLM usage")
