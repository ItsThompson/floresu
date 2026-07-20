"""HTTP adapter for sources, mounted on both apps with per-boundary identity.

Thin handlers: each resolves the caller's ``user_id`` and :class:`Actor` through
injected dependencies and calls exactly one :class:`SourceService` method. The
external app injects the cookie identity and a human actor; the internal app
injects the trusted-header identity and the named-agent actor. Business rules,
the transaction, and the write-event publish all live in the service, so both
boundaries share one implementation and provenance is uniform.

The ``FloresuError`` the service raises is rendered as RFC 9457 problem+json by
the shared exception handler.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends

from floresu.core.actor import Actor
from floresu.profile.config import DEFAULT_LIST_LIMIT
from floresu.profile.models import SourceKind
from floresu.profile.schemas import (
    ReorderRequest,
    SourceRecord,
    SourceSummary,
    SourceWrite,
)
from floresu.profile.service import SourceService

# FastAPI dependencies, injected so the router never hard-codes how identity, the
# actor, or the service are resolved (they differ per app).
Identity = Callable[..., Any]  # resolves user_id (str): async on web, sync internal
ActorResolver = Callable[..., Any]  # resolves the Actor (human vs named agent)
SourceServiceProvider = Callable[..., Any]

SOURCES_PATH = "/sources"


def create_sources_router(
    service_provider: SourceServiceProvider,
    *,
    identity: Identity,
    actor: ActorResolver,
) -> APIRouter:
    """Build the /sources router, injecting the service, identity, and actor."""
    router = APIRouter(prefix=SOURCES_PATH, tags=["sources"])

    @router.post("", status_code=201)
    async def create_source(
        body: SourceWrite,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: SourceService = Depends(service_provider),
    ) -> SourceRecord:
        return await service.create(user_id, actor_, body)

    @router.get("")
    async def list_sources(
        user_id: str = Depends(identity),
        service: SourceService = Depends(service_provider),
        kind: SourceKind | None = None,
        include_archived: bool = False,
    ) -> list[SourceSummary]:
        return await service.list_sources(
            user_id, kind=kind, include_archived=include_archived, limit=DEFAULT_LIST_LIMIT
        )

    @router.post("/reorder")
    async def reorder_sources(
        body: ReorderRequest,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: SourceService = Depends(service_provider),
    ) -> list[SourceSummary]:
        return await service.reorder(user_id, actor_, body)

    @router.get("/{source_id}")
    async def get_source(
        source_id: int,
        user_id: str = Depends(identity),
        service: SourceService = Depends(service_provider),
    ) -> SourceRecord:
        return await service.get(user_id, source_id)

    @router.put("/{source_id}")
    async def update_source(
        source_id: int,
        body: SourceWrite,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: SourceService = Depends(service_provider),
    ) -> SourceRecord:
        return await service.update(user_id, source_id, actor_, body)

    @router.post("/{source_id}/archive")
    async def archive_source(
        source_id: int,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: SourceService = Depends(service_provider),
    ) -> SourceRecord:
        return await service.archive(user_id, source_id, actor_)

    @router.post("/{source_id}/restore")
    async def restore_source(
        source_id: int,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: SourceService = Depends(service_provider),
    ) -> SourceRecord:
        return await service.restore(user_id, source_id, actor_)

    return router
