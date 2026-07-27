"""
Quota-aware multi-provider LLM gateway (free-tier first).

Every completion in the app flows through :func:`chat` (usually via the
``services.llm`` facade). The gateway holds a catalog of models across
OpenAI-compatible providers — Groq, Cerebras, Gemini, Moonshot, OpenRouter,
DeepSeek, OpenAI — and, per *purpose* (chat, brief, extraction, agent,
reviewer, fast, …), walks an ordered candidate chain:

1. skip providers with no API key configured;
2. skip models cooling down after a recent 429/5xx/auth error;
3. reserve quota (RPM + RPD counters in Postgres via the SECURITY DEFINER
   ``bump_llm_quota()``; in-process fallback when the DB is unavailable) —
   models at their published free-tier limit are skipped *before* the
   request is sent, so the app degrades down the chain instead of hammering
   providers with 429s;
4. call the provider; on success record usage and return, on failure apply
   a cooldown and try the next candidate.

Design notes:
- All providers speak the OpenAI chat-completions dialect (Gemini via its
  ``/v1beta/openai`` compatibility endpoint), so one small httpx client
  covers everything — no per-provider SDKs.
- OpenAI is an optional plug-in like any other provider: set
  ``OPENAI_API_KEY`` and it joins the end of the chains; unset it and the
  app runs entirely on free tiers.
- Free-tier limits below are set ~10-20% under the published caps so clock
  skew and multi-instance overlap don't produce provider-side 429s.
- Routes and model ids are env-overridable (``LLM_ROUTE_<PURPOSE>``,
  ``<PROVIDER>_BASE_URL``, and the ``*_MODEL`` variables read in the
  catalog) so provider changes are config, not code.

Secrets never appear in logs: failures log provider/model/status only.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

import httpx

logger = logging.getLogger("jarvis.gateway")


class GatewayUnavailableError(RuntimeError):
    """All candidate providers failed or were unavailable for a request."""


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    base_url: str
    key_envs: tuple  # first env var that is set wins


_PROVIDERS: dict[str, ProviderSpec] = {
    "groq": ProviderSpec("groq", "https://api.groq.com/openai/v1", ("GROQ_API_KEY",)),
    "cerebras": ProviderSpec("cerebras", "https://api.cerebras.ai/v1", ("CEREBRAS_API_KEY",)),
    "gemini": ProviderSpec(
        "gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    ),
    "moonshot": ProviderSpec("moonshot", "https://api.moonshot.ai/v1", ("MOONSHOT_API_KEY",)),
    "openrouter": ProviderSpec("openrouter", "https://openrouter.ai/api/v1", ("OPENROUTER_API_KEY",)),
    "deepseek": ProviderSpec("deepseek", "https://api.deepseek.com/v1", ("DEEPSEEK_API_KEY",)),
    "openai": ProviderSpec("openai", "https://api.openai.com/v1", ("OPENAI_API_KEY",)),
}


def provider_api_key(provider: str) -> Optional[str]:
    spec = _PROVIDERS.get(provider)
    if spec is None:
        return None
    for env in spec.key_envs:
        value = (os.environ.get(env) or "").strip()
        if value:
            return value
    return None


def provider_base_url(provider: str) -> str:
    override = (os.environ.get(f"{provider.upper()}_BASE_URL") or "").strip()
    return override or _PROVIDERS[provider].base_url


# ---------------------------------------------------------------------------
# Model catalog
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelSpec:
    key: str        # stable handle used in routes, e.g. "groq:llama-3.3-70b"
    provider: str
    model: str      # provider-side model id
    family: str     # model family for cross-model review (llama, kimi, gemini, ...)
    rpm: int        # conservative requests/minute cap (0 = uncapped)
    rpd: int        # conservative requests/day cap (0 = uncapped)
    # "model": counters are per model id (Groq-style per-model limits).
    # "provider": counters are shared account-wide (OpenRouter :free pool).
    quota_scope: str = "model"

    @property
    def label(self) -> str:
        """Human/audit-facing identifier, e.g. ``groq/llama-3.3-70b-versatile``."""
        return f"{self.provider}/{self.model}"

    @property
    def quota_model_key(self) -> str:
        return "__account__" if self.quota_scope == "provider" else self.model


def _env(name: str, default: str) -> str:
    return (os.environ.get(name) or "").strip() or default


def _openrouter_rpd() -> int:
    # 50/day free, 1,000/day once the account has ever bought $10 of credits.
    unlocked = (os.environ.get("OPENROUTER_UNLOCKED") or "").strip().lower() in ("1", "true", "yes")
    return 900 if unlocked else 40


def catalog() -> dict[str, ModelSpec]:
    """The model catalog (rebuilt per call: model ids are env-overridable).

    Default ids were verified against live provider /models listings
    (Jul 2026); an id a provider stops serving comes back as a 404 →
    config-class cooldown → next candidate, so drift degrades gracefully.
    """
    specs = [
        # --- Groq (per-model daily caps stack; fastest inference) ---
        ModelSpec("groq:llama-3.1-8b", "groq",
                  _env("GROQ_SMALL_MODEL", "llama-3.1-8b-instant"), "llama", 25, 12000),
        ModelSpec("groq:llama-3.3-70b", "groq",
                  _env("GROQ_LARGE_MODEL", "llama-3.3-70b-versatile"), "llama", 25, 800),
        ModelSpec("groq:gpt-oss-120b", "groq",
                  _env("GROQ_GPTOSS_MODEL", "openai/gpt-oss-120b"), "gpt-oss", 25, 800),
        ModelSpec("groq:qwen3", "groq",
                  _env("GROQ_QWEN_MODEL", "qwen/qwen3.6-27b"), "qwen", 25, 800),
        # --- Cerebras (second fast provider; big daily pool) ---
        ModelSpec("cerebras:glm-4.7", "cerebras",
                  _env("CEREBRAS_GLM_MODEL", "zai-glm-4.7"), "glm", 25, 12000),
        ModelSpec("cerebras:gpt-oss-120b", "cerebras",
                  _env("CEREBRAS_GPTOSS_MODEL", "gpt-oss-120b"), "gpt-oss", 25, 12000),
        ModelSpec("cerebras:gemma-4-31b", "cerebras",
                  _env("CEREBRAS_GEMMA_MODEL", "gemma-4-31b"), "gemma", 25, 12000),
        # --- Gemini (1M context; the long-document workhorse) ---
        ModelSpec("gemini:flash", "gemini",
                  _env("GEMINI_FLASH_MODEL", "gemini-2.5-flash"), "gemini", 8, 200),
        ModelSpec("gemini:flash-lite", "gemini",
                  _env("GEMINI_FLASH_LITE_MODEL", "gemini-2.5-flash-lite"), "gemini", 12, 800),
        # --- Moonshot first-party free tier (demo workspaces only) ---
        ModelSpec("moonshot:kimi-k2", "moonshot",
                  _env("MOONSHOT_MODEL", "kimi-k2.6"), "kimi", 3, 800),
        # --- OpenRouter :free pool (account-wide daily cap) ---
        ModelSpec("openrouter:deepseek-v3", "openrouter",
                  _env("OPENROUTER_DEEPSEEK_MODEL", "deepseek/deepseek-chat-v3-0324:free"),
                  "deepseek", 15, _openrouter_rpd(), quota_scope="provider"),
        ModelSpec("openrouter:llama-3.3-70b", "openrouter",
                  _env("OPENROUTER_LLAMA_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
                  "llama", 15, _openrouter_rpd(), quota_scope="provider"),
        # --- Paid break-glass (only used when a key is deliberately set) ---
        ModelSpec("deepseek:chat", "deepseek",
                  _env("DEEPSEEK_MODEL", "deepseek-chat"), "deepseek", 60, 0),
        ModelSpec("openai:gpt-4o-mini", "openai", "gpt-4o-mini", "gpt", 200, 0),
        ModelSpec("openai:gpt-4o", "openai", "gpt-4o", "gpt", 200, 0),
    ]
    return {spec.key: spec for spec in specs}


# ---------------------------------------------------------------------------
# Purpose routing
# ---------------------------------------------------------------------------

# Ordered candidate chains per purpose. Overridable per purpose via
# LLM_ROUTE_<PURPOSE> = comma-separated catalog keys.
_DEFAULT_ROUTES: dict[str, list[str]] = {
    # Grounded synthesis over structured + RAG context.
    "chat": [
        "groq:llama-3.3-70b", "cerebras:glm-4.7", "gemini:flash",
        "openrouter:deepseek-v3", "groq:llama-3.1-8b", "deepseek:chat", "openai:gpt-4o-mini",
    ],
    "brief": [
        "groq:llama-3.3-70b", "cerebras:glm-4.7", "gemini:flash",
        "openrouter:deepseek-v3", "deepseek:chat", "openai:gpt-4o-mini",
    ],
    "draft": [
        "groq:llama-3.3-70b", "cerebras:glm-4.7", "gemini:flash-lite",
        "openrouter:llama-3.3-70b", "deepseek:chat", "openai:gpt-4o-mini",
    ],
    # Long-document JSON extraction: context window first.
    "extraction": [
        "gemini:flash", "groq:llama-3.3-70b", "cerebras:glm-4.7",
        "moonshot:kimi-k2", "deepseek:chat", "openai:gpt-4o-mini",
    ],
    # Agent planner / tool loops: strongest free tool-callers first
    # (GPT-OSS-120B on Groq for speed, GLM-4.7 on Cerebras for capability).
    "agent": [
        "groq:gpt-oss-120b", "cerebras:glm-4.7", "gemini:flash",
        "cerebras:gpt-oss-120b", "moonshot:kimi-k2", "deepseek:chat", "openai:gpt-4o-mini",
    ],
    # Cross-model critique: routed with exclude_families=<generator family>,
    # so keep several distinct families available (gemini/qwen/gemma/llama).
    "reviewer": [
        "gemini:flash-lite", "gemini:flash", "groq:qwen3",
        "cerebras:gemma-4-31b", "groq:llama-3.3-70b", "openai:gpt-4o-mini",
    ],
    # Cheap, low-latency classification / labelling.
    "fast": [
        "groq:llama-3.1-8b", "cerebras:glm-4.7", "gemini:flash-lite",
        "openrouter:llama-3.3-70b", "openai:gpt-4o-mini",
    ],
}

_FALLBACK_ROUTE_PURPOSE = "chat"


def route_for(purpose: str) -> list[str]:
    override = (os.environ.get(f"LLM_ROUTE_{purpose.upper()}") or "").strip()
    if override:
        return [key.strip() for key in override.split(",") if key.strip()]
    return list(_DEFAULT_ROUTES.get(purpose) or _DEFAULT_ROUTES[_FALLBACK_ROUTE_PURPOSE])


# ---------------------------------------------------------------------------
# Quota accounting (Postgres first, in-process fallback)
# ---------------------------------------------------------------------------

_MINUTE = 60.0
_DAY = 86400.0

_quota_lock = threading.Lock()
# (provider, model, kind) -> [window_start_epoch, count]
_memory_counters: dict = {}


def _memory_bump(spec: ModelSpec) -> bool:
    """In-process sliding-window counters (fallback / LLM_QUOTA_BACKEND=memory)."""
    now = time.time()
    with _quota_lock:
        ok = True
        for kind, span, limit in (("minute", _MINUTE, spec.rpm), ("day", _DAY, spec.rpd)):
            if limit <= 0:
                continue
            key = (spec.provider, spec.quota_model_key, kind)
            window = _memory_counters.get(key)
            if window is None or now - window[0] >= span:
                window = [now, 0]
                _memory_counters[key] = window
            if window[1] + 1 > limit:
                ok = False
        if ok:
            for kind, _span, limit in (("minute", _MINUTE, spec.rpm), ("day", _DAY, spec.rpd)):
                if limit <= 0:
                    continue
                _memory_counters[(spec.provider, spec.quota_model_key, kind)][1] += 1
        return ok


def _postgres_bump(spec: ModelSpec) -> bool:
    from app.context import system_context
    from app.db import get_cursor

    # Global platform state: bump_llm_quota() is SECURITY DEFINER, so the
    # bootstrap (no-org) context is correct here, mirroring jobs.claim_next().
    bootstrap = system_context("")
    with get_cursor(commit=True, ctx=bootstrap) as cur:
        cur.execute(
            "SELECT bump_llm_quota(%s, %s, %s, %s) AS allowed",
            (spec.provider, spec.quota_model_key, spec.rpm, spec.rpd),
        )
        row = cur.fetchone()
    return bool(row and row.get("allowed"))


def _reserve_quota(spec: ModelSpec) -> bool:
    """True when the request fits this model's free-tier budget right now.

    Fault-tolerant by design: if the Postgres counters are unreachable the
    in-process counters take over — a degraded-but-working gateway beats a
    hard dependency of every LLM call on one extra query.
    """
    if spec.rpm <= 0 and spec.rpd <= 0:
        return True
    backend = (os.environ.get("LLM_QUOTA_BACKEND") or "postgres").strip().lower()
    if backend != "memory":
        try:
            return _postgres_bump(spec)
        except Exception:
            logger.warning("Quota counter unavailable; using in-process fallback", exc_info=True)
    return _memory_bump(spec)


# ---------------------------------------------------------------------------
# Cooldowns (in-process): stop retrying a failing provider/model for a while
# ---------------------------------------------------------------------------

_COOLDOWN_RATE_LIMIT = 65.0     # provider told us to slow down
_COOLDOWN_SERVER_ERROR = 20.0   # transient 5xx / network trouble
_COOLDOWN_CONFIG_ERROR = 900.0  # bad key / unknown model: don't hammer

_cooldown_lock = threading.Lock()
_cooldowns: dict = {}  # (provider, model) -> monotonic epoch when usable again


def _in_cooldown(spec: ModelSpec) -> bool:
    with _cooldown_lock:
        until = _cooldowns.get((spec.provider, spec.model))
        return until is not None and time.monotonic() < until


def _set_cooldown(spec: ModelSpec, seconds: float) -> None:
    with _cooldown_lock:
        _cooldowns[(spec.provider, spec.model)] = time.monotonic() + seconds


def reset_for_tests() -> None:
    """Clear cooldowns and in-process quota counters (test helper)."""
    with _cooldown_lock:
        _cooldowns.clear()
    with _quota_lock:
        _memory_counters.clear()


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

_http_lock = threading.Lock()
_http_client: Optional[httpx.Client] = None

# Test seam: swap the transport without monkeypatching httpx globally.
_transport_factory: Optional[Callable[[], httpx.BaseTransport]] = None


def set_transport_factory_for_tests(factory: Optional[Callable[[], httpx.BaseTransport]]) -> None:
    global _transport_factory, _http_client
    with _http_lock:
        _transport_factory = factory
        if _http_client is not None:
            _http_client.close()
        _http_client = None


def _client() -> httpx.Client:
    global _http_client
    if _http_client is None:
        with _http_lock:
            if _http_client is None:
                # Bounded for Lambda: a hung provider call must fit inside the
                # 180s API budget with headroom for one fallback attempt.
                read_timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "60"))
                timeout = httpx.Timeout(read_timeout, connect=10.0)
                transport = _transport_factory() if _transport_factory else None
                _http_client = httpx.Client(timeout=timeout, transport=transport)
    return _http_client


def _gateway_deadline_seconds() -> float:
    """Overall wall-clock budget for one chat() call across every candidate.

    A single hung request can still take up to LLM_TIMEOUT_SECONDS (each
    candidate's own read timeout) — this doesn't preempt an in-flight call.
    What it stops is the chain trying candidate after candidate during a
    multi-provider outage: without it, a run through N candidates that each
    time out could approach N * LLM_TIMEOUT_SECONDS, which on the API Lambda's
    synchronous /api/chat and /api/chat/brief paths (180s timeout) risks the
    request being killed mid-call — billed for the full duration with no
    usable response. Read fresh per call (not cached) so it's easy to
    override for a single request class if ever needed, and so tests can
    monkeypatch it. Always effective even at 0 (see chat(): the first
    eligible candidate is never skipped by the deadline).
    """
    return float(os.environ.get("LLM_GATEWAY_DEADLINE_SECONDS", "90"))


def _request_headers(spec: ModelSpec, api_key: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if spec.provider == "openrouter":
        # OpenRouter attribution headers (recommended; improves free-tier QoS).
        headers["HTTP-Referer"] = os.environ.get("OPENROUTER_SITE_URL", "https://kritifin.obliviox.in")
        headers["X-Title"] = os.environ.get("OPENROUTER_APP_NAME", "KritiFin")
    return headers


# ---------------------------------------------------------------------------
# Result type + the main entrypoint
# ---------------------------------------------------------------------------


@dataclass
class GatewayResult:
    content: str
    provider: str
    model: str
    purpose: str
    usage: Optional[dict] = None          # {prompt_tokens, completion_tokens, total_tokens}
    tool_calls: list = field(default_factory=list)  # raw OpenAI-style tool_call dicts
    finish_reason: str = ""
    latency_ms: int = 0

    @property
    def label(self) -> str:
        return f"{self.provider}/{self.model}"


class _Usage:
    """Duck-typed .usage for llm_usage.record_usage (dict → attributes)."""

    def __init__(self, data: dict):
        self.prompt_tokens = int(data.get("prompt_tokens") or 0)
        self.completion_tokens = int(data.get("completion_tokens") or 0)
        self.total_tokens = int(
            data.get("total_tokens") or (self.prompt_tokens + self.completion_tokens)
        )


def _candidates(
    purpose: str,
    pinned_model: Optional[str],
    exclude_families: Iterable[str],
) -> list[ModelSpec]:
    """Resolve the ordered, de-duplicated candidate list for this request."""
    cat = catalog()
    excluded = {f for f in exclude_families if f}
    ordered: list[ModelSpec] = []
    seen: set = set()

    def _push(spec: Optional[ModelSpec]) -> None:
        if spec is None or spec.key in seen or spec.family in excluded:
            return
        seen.add(spec.key)
        ordered.append(spec)

    if pinned_model:
        # A pinned model (env override like LLM_MODEL / BRIEF_LLM_MODEL) goes
        # first; the purpose chain still backs it up. Unknown names map onto
        # OpenAI for backwards compatibility with the pre-gateway config.
        match = next(
            (s for s in cat.values() if s.model == pinned_model or s.key == pinned_model), None
        )
        if match is not None:
            _push(match)
        else:
            _push(ModelSpec(f"openai:{pinned_model}", "openai", pinned_model, "gpt", 200, 0))

    for key in route_for(purpose):
        _push(cat.get(key))
    return ordered


def _parse_response(payload: dict, spec: ModelSpec, purpose: str, latency_ms: int) -> GatewayResult:
    choices = payload.get("choices") or []
    message = (choices[0].get("message") or {}) if choices else {}
    content = message.get("content") or ""
    tool_calls = message.get("tool_calls") or []
    finish = (choices[0].get("finish_reason") or "") if choices else ""
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
    return GatewayResult(
        content=content.strip() if isinstance(content, str) else "",
        provider=spec.provider,
        model=spec.model,
        purpose=purpose,
        usage=usage,
        tool_calls=tool_calls if isinstance(tool_calls, list) else [],
        finish_reason=finish,
        latency_ms=latency_ms,
    )


def chat(
    *,
    messages: list,
    purpose: str = "chat",
    max_tokens: int = 900,
    temperature: Optional[float] = None,
    model: Optional[str] = None,
    tools: Optional[list] = None,
    tool_choice: Optional[Any] = None,
    response_format: Optional[dict] = None,
    exclude_families: Iterable[str] = (),
) -> GatewayResult:
    """Run one chat completion through the routing chain for ``purpose``.

    Raises :class:`GatewayUnavailableError` when every candidate is
    unavailable (no keys, quota exhausted, cooling down, or erroring).
    """
    from app.services.llm_usage import record_usage

    candidates = _candidates(purpose, model, exclude_families)
    if not candidates:
        raise GatewayUnavailableError(f"No models routed for purpose {purpose!r}")

    errors: list[str] = []
    deadline = time.monotonic() + _gateway_deadline_seconds()
    attempted = 0
    for spec in candidates:
        api_key = provider_api_key(spec.provider)
        if not api_key:
            continue
        if _in_cooldown(spec):
            errors.append(f"{spec.label}: cooling down")
            continue
        if not _reserve_quota(spec):
            errors.append(f"{spec.label}: quota exhausted")
            continue
        # Never skip the first attempt (a request must always get at least
        # one try), but stop advancing further down the chain once the
        # overall budget is spent — see _gateway_deadline_seconds().
        if attempted > 0 and time.monotonic() >= deadline:
            errors.append(f"{spec.label}: skipped, gateway time budget exceeded")
            logger.warning(
                "LLM gateway time budget exceeded after %d attempt(s) for purpose %r; "
                "stopping fallback chain",
                attempted, purpose,
            )
            break
        attempted += 1

        body: dict[str, Any] = {
            "model": spec.model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            body["temperature"] = temperature
        if tools:
            body["tools"] = tools
            if tool_choice is not None:
                body["tool_choice"] = tool_choice
        if response_format:
            body["response_format"] = response_format

        url = f"{provider_base_url(spec.provider)}/chat/completions"
        started = time.monotonic()
        try:
            response = _client().post(url, json=body, headers=_request_headers(spec, api_key))
        except Exception as exc:
            _set_cooldown(spec, _COOLDOWN_SERVER_ERROR)
            errors.append(f"{spec.label}: network error {type(exc).__name__}")
            logger.warning("LLM call failed: %s network error %s", spec.label, type(exc).__name__)
            continue
        latency_ms = round((time.monotonic() - started) * 1000)

        if response.status_code == 200:
            try:
                result = _parse_response(response.json(), spec, purpose, latency_ms)
            except Exception:
                _set_cooldown(spec, _COOLDOWN_SERVER_ERROR)
                errors.append(f"{spec.label}: unparseable response")
                logger.warning("LLM response unparseable from %s", spec.label)
                continue
            if result.usage:
                record_usage(
                    model=spec.model,
                    purpose=purpose,
                    usage=_Usage(result.usage),
                    provider=spec.provider,
                )
            logger.info(
                "llm_call provider=%s model=%s purpose=%s latency_ms=%d",
                spec.provider, spec.model, purpose, latency_ms,
                extra={
                    "event": "llm_call",
                    "provider": spec.provider,
                    "model": spec.model,
                    "purpose": purpose,
                    "latency_ms": latency_ms,
                },
            )
            _emit_generation(spec, purpose, messages, result, None)
            return result

        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            try:
                cooldown = max(float(retry_after), 5.0) if retry_after else _COOLDOWN_RATE_LIMIT
            except ValueError:
                cooldown = _COOLDOWN_RATE_LIMIT
            _set_cooldown(spec, cooldown)
            errors.append(f"{spec.label}: 429")
            logger.warning("LLM 429 from %s; cooling %.0fs", spec.label, cooldown)
            continue
        if response.status_code in (401, 403, 404, 400, 422):
            # Bad key, unknown model, or unsupported parameter shape for this
            # provider — configuration-class problems; park it for a while.
            _set_cooldown(spec, _COOLDOWN_CONFIG_ERROR)
            errors.append(f"{spec.label}: HTTP {response.status_code}")
            logger.warning("LLM config-class error %s from %s", response.status_code, spec.label)
            continue
        _set_cooldown(spec, _COOLDOWN_SERVER_ERROR)
        errors.append(f"{spec.label}: HTTP {response.status_code}")
        logger.warning("LLM server error %s from %s", response.status_code, spec.label)

    detail = "; ".join(errors) if errors else "no provider API keys configured"
    _emit_generation(None, purpose, messages, None, detail)
    raise GatewayUnavailableError(f"All LLM candidates failed for {purpose!r}: {detail}")


# ---------------------------------------------------------------------------
# Observability seam (wired to Langfuse in services/tracing.py)
# ---------------------------------------------------------------------------

_generation_hooks: list = []


def add_generation_hook(hook: Callable[..., None]) -> None:
    """Register hook(spec, purpose, messages, result, error). Idempotent per
    function identity so repeated install() calls never double-fire events."""
    if hook not in _generation_hooks:
        _generation_hooks.append(hook)


def _emit_generation(spec, purpose, messages, result, error) -> None:
    for hook in _generation_hooks:
        try:
            hook(spec=spec, purpose=purpose, messages=messages, result=result, error=error)
        except Exception:  # noqa: BLE001 - observability must never break calls
            logger.exception("Generation hook failed")


def configured_providers() -> list[str]:
    """Providers with an API key set (for posture/status reporting)."""
    return [name for name in _PROVIDERS if provider_api_key(name)]


def family_of(provider: str, model: str) -> str:
    """Model family for a provider/model pair (used for cross-model review)."""
    for spec in catalog().values():
        if spec.provider == provider and spec.model == model:
            return spec.family
    return provider


def dumps_route_table() -> str:
    """Debug/status helper: the effective route table as JSON."""
    return json.dumps({p: route_for(p) for p in _DEFAULT_ROUTES}, indent=2)
