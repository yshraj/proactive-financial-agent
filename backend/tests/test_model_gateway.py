"""Quota-aware model gateway (services/model_gateway.py).

Pure unit tests: no DB (LLM_QUOTA_BACKEND=memory via conftest), no network
(httpx.MockTransport injected through the test seam).
"""
from __future__ import annotations

import json
import logging

import httpx
import pytest

from app.services import model_gateway
from app.services.model_gateway import GatewayUnavailableError, ModelSpec


@pytest.fixture(autouse=True)
def _clean_gateway():
    model_gateway.reset_for_tests()
    yield
    model_gateway.set_transport_factory_for_tests(None)
    model_gateway.reset_for_tests()


def _install(handler) -> None:
    model_gateway.set_transport_factory_for_tests(lambda: httpx.MockTransport(handler))


def _ok_payload(content: str = "Hello", model: str = "m") -> dict:
    return {
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
        "model": model,
    }


def test_routes_to_first_configured_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_ok_payload("  Answer.  "))

    _install(handler)
    result = model_gateway.chat(
        messages=[{"role": "user", "content": "hi"}], purpose="chat", max_tokens=100
    )
    assert result.provider == "groq"
    assert result.model == "llama-3.3-70b-versatile"
    assert result.content == "Answer."
    assert seen["host"] == "api.groq.com"
    assert seen["auth"] == "Bearer gsk-test"
    assert seen["body"]["model"] == "llama-3.3-70b-versatile"
    assert seen["body"]["max_tokens"] == 100


def test_falls_back_on_429_and_remembers_cooldown(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("CEREBRAS_API_KEY", "csk-test")
    hits = {"groq": 0, "cerebras": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.groq.com":
            hits["groq"] += 1
            return httpx.Response(429, headers={"retry-after": "30"}, json={"error": "slow down"})
        hits["cerebras"] += 1
        return httpx.Response(200, json=_ok_payload("From Cerebras"))

    _install(handler)
    first = model_gateway.chat(
        messages=[{"role": "user", "content": "hi"}], purpose="chat", max_tokens=64
    )
    assert first.provider == "cerebras"
    assert hits == {"groq": 1, "cerebras": 1}

    # Second call: groq is cooling down, goes straight to cerebras.
    second = model_gateway.chat(
        messages=[{"role": "user", "content": "hi again"}], purpose="chat", max_tokens=64
    )
    assert second.provider == "cerebras"
    assert hits == {"groq": 1, "cerebras": 2}


def test_no_configured_providers_raises(monkeypatch):
    _install(lambda request: httpx.Response(200, json=_ok_payload()))
    with pytest.raises(GatewayUnavailableError):
        model_gateway.chat(
            messages=[{"role": "user", "content": "hi"}], purpose="chat", max_tokens=64
        )


def test_pinned_model_goes_first_even_off_route(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        seen["model"] = json.loads(request.content)["model"]
        return httpx.Response(200, json=_ok_payload())

    _install(handler)
    result = model_gateway.chat(
        messages=[{"role": "user", "content": "hi"}],
        purpose="chat",
        max_tokens=64,
        model="gpt-4o-mini",
    )
    assert result.provider == "openai"
    assert seen == {"host": "api.openai.com", "model": "gpt-4o-mini"}


def test_unknown_pinned_model_maps_to_openai_for_back_compat(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["model"] = json.loads(request.content)["model"]
        return httpx.Response(200, json=_ok_payload())

    _install(handler)
    result = model_gateway.chat(
        messages=[{"role": "user", "content": "hi"}],
        purpose="chat",
        max_tokens=64,
        model="ft:my-custom-model",
    )
    assert result.provider == "openai"
    assert seen["model"] == "ft:my-custom-model"


def test_exclude_families_for_cross_model_review(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        seen["model"] = json.loads(request.content)["model"]
        return httpx.Response(200, json=_ok_payload())

    _install(handler)
    result = model_gateway.chat(
        messages=[{"role": "user", "content": "review this"}],
        purpose="reviewer",
        max_tokens=64,
        exclude_families=("gemini",),
    )
    # Reviewer route prefers Gemini, but the generator was Gemini-family, so
    # the critique must come from a different family.
    assert result.provider == "groq"
    assert result.model == "qwen/qwen3.6-27b"


def test_memory_quota_minute_and_day_limits():
    spec = ModelSpec("t:m", "testprov", "m1", "fam", rpm=1, rpd=0)
    assert model_gateway._memory_bump(spec) is True
    assert model_gateway._memory_bump(spec) is False  # same minute window

    daily = ModelSpec("t:d", "testprov", "m2", "fam", rpm=0, rpd=2)
    assert model_gateway._memory_bump(daily) is True
    assert model_gateway._memory_bump(daily) is True
    assert model_gateway._memory_bump(daily) is False


def test_openrouter_free_pool_is_shared_across_models():
    a = ModelSpec("or:a", "openrouter", "x:free", "deepseek", rpm=0, rpd=2, quota_scope="provider")
    b = ModelSpec("or:b", "openrouter", "y:free", "llama", rpm=0, rpd=2, quota_scope="provider")
    assert model_gateway._memory_bump(a) is True
    assert model_gateway._memory_bump(b) is True
    # Third request across EITHER model exceeds the shared account cap.
    assert model_gateway._memory_bump(a) is False
    assert model_gateway._memory_bump(b) is False


def test_quota_exhausted_model_is_skipped_in_routing(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("CEREBRAS_API_KEY", "csk-test")
    hits = {"groq": 0, "cerebras": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        key = "groq" if request.url.host == "api.groq.com" else "cerebras"
        hits[key] += 1
        return httpx.Response(200, json=_ok_payload())

    _install(handler)
    # Exhaust groq's llama-3.3-70b minute budget artificially.
    spec = model_gateway.catalog()["groq:llama-3.3-70b"]
    for _ in range(spec.rpm):
        assert model_gateway._memory_bump(spec) is True

    result = model_gateway.chat(
        messages=[{"role": "user", "content": "hi"}], purpose="chat", max_tokens=64
    )
    assert result.provider == "cerebras"
    assert hits == {"groq": 0, "cerebras": 1}


def test_tool_calls_are_surfaced(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "search_documents", "arguments": "{\"q\": \"isa\"}"},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 30, "completion_tokens": 12, "total_tokens": 42},
        })

    _install(handler)
    result = model_gateway.chat(
        messages=[{"role": "user", "content": "hi"}],
        purpose="agent",
        max_tokens=64,
        tools=[{"type": "function", "function": {"name": "search_documents", "parameters": {}}}],
    )
    assert result.finish_reason == "tool_calls"
    assert result.content == ""
    assert result.tool_calls[0]["function"]["name"] == "search_documents"


def test_usage_event_carries_provider(monkeypatch, caplog):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    _install(lambda request: httpx.Response(200, json=_ok_payload()))
    with caplog.at_level(logging.INFO, logger="jarvis.llm_usage"):
        model_gateway.chat(
            messages=[{"role": "user", "content": "hi"}], purpose="chat", max_tokens=64
        )
    [record] = [r for r in caplog.records if getattr(r, "event", "") == "llm_usage"]
    assert record.provider == "groq"
    assert record.total_tokens == 16
    assert record.est_cost_usd == 0.0  # free tier prices as zero


def test_config_error_parks_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-bad")
    monkeypatch.setenv("CEREBRAS_API_KEY", "csk-test")
    hits = {"groq": 0, "cerebras": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.groq.com":
            hits["groq"] += 1
            return httpx.Response(401, json={"error": "invalid api key"})
        hits["cerebras"] += 1
        return httpx.Response(200, json=_ok_payload())

    _install(handler)
    for _ in range(2):
        result = model_gateway.chat(
            messages=[{"role": "user", "content": "hi"}], purpose="chat", max_tokens=64
        )
        assert result.provider == "cerebras"
    assert hits["groq"] == 1  # parked after the first auth failure


def test_route_env_override(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    monkeypatch.setenv("LLM_ROUTE_CHAT", "gemini:flash-lite")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["model"] = json.loads(request.content)["model"]
        return httpx.Response(200, json=_ok_payload())

    _install(handler)
    result = model_gateway.chat(
        messages=[{"role": "user", "content": "hi"}], purpose="chat", max_tokens=64
    )
    assert result.provider == "gemini"
    assert seen["model"] == "gemini-2.5-flash-lite"


def test_llm_facade_wraps_gateway_errors(monkeypatch):
    from app.services.llm import AIUnavailableError, complete_with_system

    _install(lambda request: httpx.Response(200, json=_ok_payload()))
    with pytest.raises(AIUnavailableError) as excinfo:
        complete_with_system(system="s", user="u", max_tokens=32)
    # Fixed public copy only — no provider detail in the message.
    assert "provider" not in str(excinfo.value).lower()
    assert "couldn't generate AI results" in str(excinfo.value)


def test_llm_facade_returns_content(monkeypatch):
    from app.services.llm import complete_with_system

    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    _install(lambda request: httpx.Response(200, json=_ok_payload("The answer.")))
    assert complete_with_system(system="s", user="u", max_tokens=32) == "The answer."
