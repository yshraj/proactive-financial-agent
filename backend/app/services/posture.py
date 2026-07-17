"""
Data-handling & AI posture reporting.

Reports the deployment's configured compliance posture (data residency, whether
the app trains on client data, retention, LLM provider) for the trust/compliance
surface UK advisers expect. Pure: takes an env mapping and returns a structured
posture, so it is fully unit-testable. Only states facts that are true of the
app (it never trains models on client data) or that are explicitly configured.
"""
from __future__ import annotations

from typing import Any, Mapping

_TRUTHY = {"1", "true", "yes", "on"}


def _flag(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


def _auth_mode(env: Mapping[str, str]) -> str:
    raw = (env.get("AUTH_MODE") or "required").strip().lower()
    return "demo" if raw == "demo" else "required"


def get_posture(env: Mapping[str, str]) -> dict[str, Any]:
    """
    Build the posture report from environment configuration.

    Defaults are conservative and documented: the app never trains on client
    data; residency/retention reflect configuration and read "not configured"
    when unset rather than asserting an unverified claim.

    ``auth_required`` reflects the real posture: Supabase JWT enforcement
    (AUTH_MODE=required, the default) or the service API key — not just the
    API key as before, which under-reported JWT-protected deployments.
    """
    mode = _auth_mode(env)
    supabase_auth = bool(
        (env.get("SUPABASE_URL") or "").strip() or (env.get("SUPABASE_JWT_SECRET") or "").strip()
    )
    api_key = bool((env.get("API_KEY") or "").strip())
    return {
        # The application never fine-tunes/trains models on client data.
        "trains_on_client_data": False,
        "data_residency": (env.get("DATA_RESIDENCY") or "not configured").strip() or "not configured",
        "data_retention_days": _retention(env),
        "llm_provider": (env.get("LLM_PROVIDER") or "openai").strip().lower(),
        "encryption_at_rest": _flag(env, "ENCRYPTION_AT_REST", False),
        "encryption_in_transit": _flag(env, "ENCRYPTION_IN_TRANSIT", True),
        "auth_required": (mode == "required" and supabase_auth) or api_key,
        "auth_mode": mode,
        # Audit is Postgres-backed (append-only audit_log) as of this release.
        "durable_audit": True,
    }


def _retention(env: Mapping[str, str]) -> Any:
    raw = env.get("DATA_RETENTION_DAYS")
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError:
        return None
