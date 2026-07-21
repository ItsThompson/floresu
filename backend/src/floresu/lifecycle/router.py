"""HTTP adapter for the web-only lifecycle, mounted on the external app ONLY.

Thin handlers: each resolves the caller's ``user_id`` (human session cookie) and
:class:`Actor` (always human here) through injected dependencies and calls exactly
one :class:`LifecycleService` method. This router is never mounted on the internal
app, so an agent has no permanent-delete, export, or account-delete route; a
boundary test asserts their absence. Business rules, the transaction, and the
write-event publish live in the service.

The destructive routes are ``DELETE`` (the method the internal app reserves for
this web-only surface) and carry a required ``confirm`` flag: the contract-level
confirmation gate. The export is a ``GET`` that streams the archive as a download.
Account deletion also clears the session cookies, since the account is gone.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse

from floresu.accounts.config import AUTH_PATH, REFRESH_COOKIE_NAME, CookieConfig
from floresu.core.actor import Actor
from floresu.core.identity import SESSION_COOKIE_NAME
from floresu.lifecycle.config import EXPORT_FILENAME_STEM
from floresu.lifecycle.schemas import AccountDeletionReceipt, DeletionReceipt
from floresu.lifecycle.service import LifecycleService

# FastAPI dependencies, injected so the router never hard-codes how identity, the
# actor, or the service are resolved. On the external app these are the cookie
# identity and the human actor; this router mounts on no other app.
Identity = Callable[..., Any]
ActorResolver = Callable[..., Any]
LifecycleServiceProvider = Callable[..., Any]

_CONFIRM = Query(description="Must be true. This action is permanent and cannot be undone.")


def create_lifecycle_router(
    service_provider: LifecycleServiceProvider,
    *,
    identity: Identity,
    actor: ActorResolver,
    cookie_config: CookieConfig,
) -> APIRouter:
    """Build the web-only lifecycle router, injecting the service, identity, and actor."""
    router = APIRouter(tags=["lifecycle"])

    @router.delete("/worklog/{worklog_id}")
    async def delete_worklog(
        worklog_id: int,
        confirm: bool = _CONFIRM,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: LifecycleService = Depends(service_provider),
    ) -> DeletionReceipt:
        return await service.permanently_delete_worklog(
            user_id, worklog_id, actor_, confirm=confirm
        )

    @router.delete("/sources/{source_id}")
    async def delete_source(
        source_id: int,
        confirm: bool = _CONFIRM,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: LifecycleService = Depends(service_provider),
    ) -> DeletionReceipt:
        return await service.permanently_delete_source(user_id, source_id, actor_, confirm=confirm)

    @router.delete("/bullets/{bullet_id}")
    async def delete_bullet(
        bullet_id: int,
        confirm: bool = _CONFIRM,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: LifecycleService = Depends(service_provider),
    ) -> DeletionReceipt:
        return await service.permanently_delete_bullet(user_id, bullet_id, actor_, confirm=confirm)

    @router.delete("/resumes/{resume_id}")
    async def delete_resume(
        resume_id: int,
        confirm: bool = _CONFIRM,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: LifecycleService = Depends(service_provider),
    ) -> DeletionReceipt:
        return await service.permanently_delete_resume(user_id, resume_id, actor_, confirm=confirm)

    @router.get("/account/export")
    async def export_account(
        user_id: str = Depends(identity),
        service: LifecycleService = Depends(service_provider),
    ) -> Response:
        archive = await service.export_data(user_id)
        filename = f"{EXPORT_FILENAME_STEM}-{date.today().isoformat()}.json"
        return JSONResponse(
            content=archive,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.delete("/account")
    async def delete_account(
        response: Response,
        confirm: bool = _CONFIRM,
        user_id: str = Depends(identity),
        service: LifecycleService = Depends(service_provider),
    ) -> AccountDeletionReceipt:
        receipt = await service.delete_account(user_id, confirm=confirm)
        _clear_session_cookies(response, cookie_config)
        return receipt

    return router


def _clear_session_cookies(response: Response, config: CookieConfig) -> None:
    """Expire both session cookies: deleting your account signs you out."""
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        domain=config.domain,
        secure=config.secure,
        httponly=True,
        samesite=config.samesite,
    )
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path=AUTH_PATH,
        domain=config.domain,
        secure=config.secure,
        httponly=True,
        samesite=config.samesite,
    )
