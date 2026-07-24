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

from fastapi import APIRouter, Depends

from floresu.accounts.schemas import AuthenticatedUser
from floresu.accounts.service import AccountService
from floresu.core.providers import Identity, ServiceProvider


def create_me_router(
    service_provider: ServiceProvider[AccountService], *, identity: Identity
) -> APIRouter:
    """Build the /me router, injecting the service provider and identity."""
    router = APIRouter(tags=["me"])

    @router.get("/me")
    async def me(
        user_id: str = Depends(identity),
        service: AccountService = Depends(service_provider),
    ) -> AuthenticatedUser:
        return await service.me(user_id)

    @router.post("/me/onboarding")
    async def complete_onboarding(
        user_id: str = Depends(identity),
        service: AccountService = Depends(service_provider),
    ) -> AuthenticatedUser:
        return await service.complete_onboarding(user_id)

    return router
