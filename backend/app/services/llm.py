"""Shared OpenAI completion helpers."""

import os
from typing import Literal, Optional

Purpose = Literal["brief", "chat", "draft"]

# Low temperature for consistent, factual adviser outputs
DEFAULT_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0"))


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

    client = get_openai_client()
    response = client.chat.completions.create(
        model=model or resolve_model(purpose),
        messages=messages,
        max_tokens=max_tokens,
        temperature=DEFAULT_TEMPERATURE if temperature is None else temperature,
    )
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
