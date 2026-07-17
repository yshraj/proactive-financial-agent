"""
Request-scoped context: request id + tenant identity.

Kept dependency-free (no DB / FastAPI imports) so it can be imported from
anywhere — db.py, logging, services — without circular imports. The values are
stored in contextvars, which Starlette propagates into threadpool-executed
sync endpoints and background tasks.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional

# The single, fixed workspace used for (a) backfilling pre-tenancy data and
# (b) the AUTH_MODE=demo shared workspace. The first real user to sign in
# claims it (see app.tenancy).
DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_ORG_NAME = "Default Workspace"

# Actor roles carried by TenantContext.role
ROLE_OWNER = "owner"
ROLE_ADVISER = "adviser"
ROLE_DEMO = "demo"
ROLE_SERVICE = "service"
ROLE_SYSTEM = "system"  # background worker / scheduled jobs


@dataclass(frozen=True)
class TenantContext:
    """Resolved tenant identity for the current request or job."""

    org_id: str
    user_id: Optional[str] = None
    role: str = ROLE_ADVISER
    email: Optional[str] = None
    request_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)


_request_id_var: "ContextVar[Optional[str]]" = ContextVar("request_id", default=None)
_tenant_var: "ContextVar[Optional[TenantContext]]" = ContextVar("tenant", default=None)


def set_request_id(request_id: Optional[str]) -> None:
    _request_id_var.set(request_id)


def get_request_id() -> Optional[str]:
    return _request_id_var.get()


def set_current_tenant(ctx: Optional[TenantContext]) -> None:
    _tenant_var.set(ctx)


def get_current_tenant() -> Optional[TenantContext]:
    return _tenant_var.get()


def require_current_tenant() -> TenantContext:
    ctx = _tenant_var.get()
    if ctx is None:
        raise RuntimeError(
            "No tenant context bound to this request/job. "
            "Endpoints must depend on app.tenancy.resolve_tenant; background jobs "
            "must call app.context.set_current_tenant() before touching data."
        )
    return ctx


def system_context(org_id: str, *, request_id: Optional[str] = None) -> TenantContext:
    """Tenant context for trusted background work acting on a specific org."""
    return TenantContext(org_id=org_id, user_id=None, role=ROLE_SYSTEM, request_id=request_id)
