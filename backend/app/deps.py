"""Shared FastAPI dependencies."""
from __future__ import annotations

from fastapi import Depends, Request

from app.auth import authenticate_request
from app.context import TenantContext


def current_tenant(
    request: Request, _: TenantContext = Depends(authenticate_request)
) -> TenantContext:
    """The tenant resolved by the router-level auth guard.

    Depending on authenticate_request directly (rather than reading state) keeps
    endpoints testable in isolation and guarantees ordering.
    """
    return request.state.tenant
