"""External REST adapter for the current-user view: GET /me.

A single thin handler in its own small router so ``accounts/api.py`` stays focused
on ``/auth/*``. It resolves the caller's ``user_id`` via the injected ``identity``
dependency (``require_user`` on the external app), calls one
:class:`AccountService` method, and returns the :class:`AuthenticatedUser`; the
``FloresuError`` the service raises is rendered as RFC 9457 problem+json by the
shared exception handler.

The route takes no request body or path id: the account is always the
session-resolved identity, never a client-supplied id. Mounted on the external
app only.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends

from floresu.accounts.schemas import AuthenticatedUser
from floresu.accounts.service import AccountService

# A FastAPI dependency that resolves the request's ``user_id`` at the trust
# boundary (``require_user`` on the external app), injected so the router never
# hard-codes how identity is resolved.
Identity = Callable[..., Awaitable[str]]
# A FastAPI dependency that yields an AccountService for the request.
AccountServiceProvider = Callable[..., object]


def create_me_router(service_provider: AccountServiceProvider, *, identity: Identity) -> APIRouter:
    """Build the /me router, injecting the service provider and identity."""
    router = APIRouter(tags=["me"])

    @router.get("/me")
    async def me(
        user_id: str = Depends(identity),
        service: AccountService = Depends(service_provider),
    ) -> AuthenticatedUser:
        return await service.me(user_id)

    return router
