"""HTTP adapter for worklog, mounted on both apps with per-boundary identity.

Thin handlers: each resolves the caller's ``user_id`` and :class:`Actor` through
injected dependencies and calls exactly one :class:`WorklogService` method. The
external app injects the cookie identity and a human actor; the internal app
injects the trusted-header identity and the named-agent actor. Business rules, the
transaction, and the write-event publish all live in the service, so both
boundaries share one implementation and provenance is uniform.

The tag-reuse read (``GET /worklog/tags``) is declared before the
``/worklog/{worklog_id}`` routes so the literal path is matched ahead of the id
parameter. The ``FloresuError`` the service raises is rendered as RFC 9457
problem+json by the shared exception handler.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends

from floresu.core.actor import Actor
from floresu.worklog.schemas import (
    TagMutation,
    TagRead,
    WorklogRecord,
    WorklogSummary,
    WorklogWrite,
)
from floresu.worklog.service import WorklogService

# FastAPI dependencies, injected so the router never hard-codes how identity, the
# actor, or the service are resolved (they differ per app).
Identity = Callable[..., Any]  # resolves user_id (str): async on web, sync internal
ActorResolver = Callable[..., Any]  # resolves the Actor (human vs named agent)
WorklogServiceProvider = Callable[..., Any]

WORKLOG_PATH = "/worklog"


def create_worklog_router(
    service_provider: WorklogServiceProvider,
    *,
    identity: Identity,
    actor: ActorResolver,
) -> APIRouter:
    """Build the /worklog router, injecting the service, identity, and actor."""
    router = APIRouter(prefix=WORKLOG_PATH, tags=["worklog"])

    @router.post("", status_code=201)
    async def create_entry(
        body: WorklogWrite,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: WorklogService = Depends(service_provider),
    ) -> WorklogRecord:
        return await service.create(user_id, actor_, body)

    @router.get("")
    async def list_entries(
        user_id: str = Depends(identity),
        service: WorklogService = Depends(service_provider),
        include_archived: bool = False,
    ) -> list[WorklogSummary]:
        # No pagination at P0 (small timelines); the service caps the read at its
        # default limit. Add a limit/cursor param here when timelines can grow.
        return await service.list_entries(user_id, include_archived=include_archived)

    @router.get("/tags")
    async def list_tags(
        user_id: str = Depends(identity),
        service: WorklogService = Depends(service_provider),
    ) -> list[TagRead]:
        return await service.list_tags(user_id)

    @router.get("/{worklog_id}")
    async def get_entry(
        worklog_id: int,
        user_id: str = Depends(identity),
        service: WorklogService = Depends(service_provider),
    ) -> WorklogRecord:
        return await service.get(user_id, worklog_id)

    @router.put("/{worklog_id}")
    async def update_entry(
        worklog_id: int,
        body: WorklogWrite,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: WorklogService = Depends(service_provider),
    ) -> WorklogRecord:
        return await service.update(user_id, worklog_id, actor_, body)

    @router.post("/{worklog_id}/archive")
    async def archive_entry(
        worklog_id: int,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: WorklogService = Depends(service_provider),
    ) -> WorklogRecord:
        return await service.archive(user_id, worklog_id, actor_)

    @router.post("/{worklog_id}/restore")
    async def restore_entry(
        worklog_id: int,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: WorklogService = Depends(service_provider),
    ) -> WorklogRecord:
        return await service.restore(user_id, worklog_id, actor_)

    @router.post("/{worklog_id}/tags")
    async def mutate_tags(
        worklog_id: int,
        body: TagMutation,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: WorklogService = Depends(service_provider),
    ) -> WorklogRecord:
        # One non-destructive POST for both actions: the agent-facing internal app
        # exposes zero DELETE routes, so remove is modeled as a POST, not a DELETE.
        if body.action == "add":
            return await service.add_tag(user_id, worklog_id, actor_, body.label)
        return await service.remove_tag(user_id, worklog_id, actor_, body.label)

    return router
