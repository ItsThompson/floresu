"""HTTP adapter for the library, mounted on both apps with per-boundary identity.

Thin handlers: each resolves the caller's ``user_id`` and :class:`Actor` through
injected dependencies and calls exactly one :class:`LibraryService` method. The
external app injects the cookie identity and a human actor; the internal app
injects the trusted-header identity and the named-agent actor. Business rules, the
transaction, and the write-event publish all live in the service, so both
boundaries share one implementation and provenance is uniform.

The ``FloresuError`` the service raises is rendered as RFC 9457 problem+json by the
shared exception handler.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends

from floresu.core.actor import Actor
from floresu.library.schemas import BulletpointRecord, BulletpointWrite
from floresu.library.service import LibraryService

# FastAPI dependencies, injected so the router never hard-codes how identity, the
# actor, or the service are resolved (they differ per app).
Identity = Callable[..., Any]  # resolves user_id (str): async on web, sync internal
ActorResolver = Callable[..., Any]  # resolves the Actor (human vs named agent)
LibraryServiceProvider = Callable[..., Any]

BULLETS_PATH = "/bullets"


def create_bullets_router(
    service_provider: LibraryServiceProvider,
    *,
    identity: Identity,
    actor: ActorResolver,
) -> APIRouter:
    """Build the /bullets router, injecting the service, identity, and actor."""
    router = APIRouter(prefix=BULLETS_PATH, tags=["library"])

    @router.post("", status_code=201)
    async def create_bullet(
        body: BulletpointWrite,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: LibraryService = Depends(service_provider),
    ) -> BulletpointRecord:
        return await service.create(user_id, actor_, body)

    @router.get("")
    async def list_bullets(
        user_id: str = Depends(identity),
        service: LibraryService = Depends(service_provider),
        include_archived: bool = False,
    ) -> list[BulletpointRecord]:
        # No pagination at P0 (small libraries); the service caps the read at its
        # default limit. Add a limit/cursor param here when libraries can grow.
        return await service.list_bullets(user_id, include_archived=include_archived)

    @router.get("/{bullet_id}")
    async def get_bullet(
        bullet_id: int,
        user_id: str = Depends(identity),
        service: LibraryService = Depends(service_provider),
    ) -> BulletpointRecord:
        return await service.get(user_id, bullet_id)

    @router.put("/{bullet_id}")
    async def update_bullet(
        bullet_id: int,
        body: BulletpointWrite,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: LibraryService = Depends(service_provider),
    ) -> BulletpointRecord:
        return await service.update(user_id, bullet_id, actor_, body)

    @router.post("/{bullet_id}/archive")
    async def archive_bullet(
        bullet_id: int,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: LibraryService = Depends(service_provider),
    ) -> BulletpointRecord:
        return await service.archive(user_id, bullet_id, actor_)

    @router.post("/{bullet_id}/restore")
    async def restore_bullet(
        bullet_id: int,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: LibraryService = Depends(service_provider),
    ) -> BulletpointRecord:
        return await service.restore(user_id, bullet_id, actor_)

    return router
