"""Langfuse tracing seam: env-gated no-op, generation hook, run traces."""
from __future__ import annotations

import httpx
import pytest

from app.services import model_gateway, tracing


class FakeLangfuse:
    def __init__(self):
        self.traces: list[dict] = []
        self.generations: list[dict] = []
        self.spans: list[dict] = []
        self.flushed = 0

    def trace(self, **kwargs):
        self.traces.append(kwargs)

    def generation(self, **kwargs):
        self.generations.append(kwargs)

    def span(self, **kwargs):
        self.spans.append(kwargs)

    def flush(self):
        self.flushed += 1


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    tracing.reset_for_tests()
    model_gateway.reset_for_tests()
    yield
    model_gateway.set_transport_factory_for_tests(None)
    model_gateway.reset_for_tests()
    tracing.reset_for_tests()


def _fake_client(monkeypatch) -> FakeLangfuse:
    fake = FakeLangfuse()
    monkeypatch.setattr(tracing, "_client", lambda: fake)
    return fake


def test_everything_is_noop_without_keys(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert tracing.enabled() is False
    # None of these may raise when unconfigured.
    tracing.start_run_trace(run_id="r1", kind="copilot", org_id="o1", query="q")
    tracing.record_step(node="plan", label="Planning", status="DONE")
    tracing.end_run_trace(output={"ok": True})
    tracing.flush()


def test_gateway_generation_events_reach_langfuse(monkeypatch):
    fake = _fake_client(monkeypatch)
    tracing.install()
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    model_gateway.set_transport_factory_for_tests(
        lambda: httpx.MockTransport(lambda request: httpx.Response(200, json={
            "choices": [{"message": {"content": "Hi"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        }))
    )
    model_gateway.chat(messages=[{"role": "user", "content": "hi"}], purpose="chat",
                       max_tokens=32)
    assert len(fake.generations) == 1
    gen = fake.generations[0]
    assert gen["name"] == "llm:chat"
    assert gen["model"] == "groq/llama-3.3-70b-versatile"
    assert gen["usage"] == {"input": 5, "output": 2}


def test_run_trace_wraps_generations_and_steps(monkeypatch):
    fake = _fake_client(monkeypatch)
    tracing.start_run_trace(run_id="run-1", kind="copilot", org_id="org-1", query="q")
    tracing.record_step(node="plan", label="Planning approach", status="DONE")
    tracing._on_generation(
        spec=None, purpose="chat", messages=[{"role": "user", "content": "hi"}],
        result=model_gateway.GatewayResult(
            content="answer", provider="groq", model="m", purpose="chat",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        ),
        error=None,
    )
    tracing.end_run_trace(output={"answer_chars": 6})

    assert fake.traces[0]["id"] == "run-1"
    assert fake.spans[0]["trace_id"] == "run-1"
    assert fake.generations[0]["trace_id"] == "run-1"
    # Trace closed: subsequent generations are standalone again.
    tracing._on_generation(spec=None, purpose="chat", messages=[], result=None, error="x")
    assert fake.generations[1]["trace_id"] is None


def test_masked_mode_hides_content(monkeypatch):
    fake = _fake_client(monkeypatch)
    monkeypatch.setenv("LANGFUSE_MASK_CONTENT", "true")
    tracing._on_generation(
        spec=None, purpose="chat",
        messages=[{"role": "user", "content": "Alan has £895,000"}],
        result=model_gateway.GatewayResult(
            content="secret answer", provider="groq", model="m", purpose="chat",
        ),
        error=None,
    )
    gen = fake.generations[0]
    assert "895" not in str(gen["input"])
    assert "secret" not in str(gen["output"])


def test_tracing_errors_never_propagate(monkeypatch):
    class ExplodingClient:
        def generation(self, **kwargs):
            raise RuntimeError("langfuse down")

        def trace(self, **kwargs):
            raise RuntimeError("langfuse down")

        def span(self, **kwargs):
            raise RuntimeError("langfuse down")

        def flush(self):
            raise RuntimeError("langfuse down")

    monkeypatch.setattr(tracing, "_client", lambda: ExplodingClient())
    tracing.start_run_trace(run_id="r", kind="copilot", org_id="o", query="q")
    tracing.record_step(node="plan", label="l", status="DONE")
    tracing._on_generation(spec=None, purpose="chat", messages=[], result=None, error=None)
    tracing.end_run_trace(output=None)
    tracing.flush()  # none of the above may raise
