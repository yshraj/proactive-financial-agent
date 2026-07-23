"""LLM token-usage accounting (services/llm_usage.py). Pure unit tests."""
from __future__ import annotations

import logging
from types import SimpleNamespace

from app.services.llm_usage import _estimate_cost_usd, record_usage


def _usage(prompt=100, completion=50, total=None):
    return SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total if total is not None else prompt + completion,
    )


# --- cost estimation -------------------------------------------------------

def test_cost_gpt4o():
    # 1M prompt + 1M completion at (2.50, 10.00)
    assert _estimate_cost_usd("gpt-4o", 1_000_000, 1_000_000) == 12.50


def test_cost_mini_not_matched_as_4o():
    # Longest-prefix match: gpt-4o-mini must use mini pricing, not gpt-4o.
    assert _estimate_cost_usd("gpt-4o-mini", 1_000_000, 0) == 0.15


def test_cost_dated_snapshot_uses_base_price():
    assert _estimate_cost_usd("gpt-4o-2024-08-06", 1_000_000, 0) == 2.50


def test_cost_unknown_model_is_zero():
    assert _estimate_cost_usd("some-future-model", 1_000_000, 1_000_000) == 0.0


def test_cost_embeddings():
    assert _estimate_cost_usd("text-embedding-3-small", 1_000_000, 0) == 0.02


# --- record_usage ----------------------------------------------------------

def test_record_usage_emits_structured_event(caplog):
    with caplog.at_level(logging.INFO, logger="jarvis.llm_usage"):
        record_usage(model="gpt-4o-mini", purpose="chat", usage=_usage(200, 100))
    [record] = [r for r in caplog.records if getattr(r, "event", "") == "llm_usage"]
    assert record.model == "gpt-4o-mini"
    assert record.purpose == "chat"
    assert record.total_tokens == 300
    assert record.prompt_tokens == 200
    assert record.completion_tokens == 100
    assert record.est_cost_usd > 0


def test_record_usage_none_is_silent(caplog):
    with caplog.at_level(logging.INFO, logger="jarvis.llm_usage"):
        record_usage(model="gpt-4o", purpose="chat", usage=None)
    assert not [r for r in caplog.records if getattr(r, "event", "") == "llm_usage"]


def test_record_usage_embeddings_shape(caplog):
    # Embedding responses have no completion_tokens attribute.
    usage = SimpleNamespace(prompt_tokens=500, total_tokens=500)
    with caplog.at_level(logging.INFO, logger="jarvis.llm_usage"):
        record_usage(model="text-embedding-3-small", purpose="embedding", usage=usage)
    [record] = [r for r in caplog.records if getattr(r, "event", "") == "llm_usage"]
    assert record.total_tokens == 500
    assert record.completion_tokens == 0


def test_record_usage_never_raises():
    class Hostile:
        @property
        def prompt_tokens(self):
            raise ValueError("boom")

    record_usage(model="gpt-4o", purpose="chat", usage=Hostile())  # must not raise
