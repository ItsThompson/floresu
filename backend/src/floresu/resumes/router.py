"""HTTP adapter for resumes, mounted on both apps with per-boundary identity.

Thin handlers: each resolves the caller's ``user_id`` and :class:`Actor` through
injected dependencies and calls exactly one :class:`ResumeService` method. The
external app injects the cookie identity and a human actor; the internal app
injects the trusted-header identity and the named-agent actor. Business rules, the
transaction, the write-event publish, and optimistic-concurrency guarding all live
in the service, so both boundaries share one implementation.

Every mutation carries the expected resume ``revision`` in the ``If-Match`` header;
a missing header is a request-validation error and a stale value is rejected by the
service as a recoverable conflict. The ``FloresuError`` the service raises is
rendered as RFC 9457 problem+json by the shared exception handler.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Header

from floresu.core.actor import Actor
from floresu.resumes.cow import EditChannel
from floresu.resumes.models import ResumeKind
from floresu.resumes.schemas import (
    AddItemRequest,
    ResumeCreateRequest,
    ResumeRecord,
    ResumeReorderRequest,
    ResumeSummary,
    ResumeUpdate,
    ScopeEditRequest,
    ScopeEditResult,
)
from floresu.resumes.service import ResumeService

# FastAPI dependencies, injected so the router never hard-codes how identity, the
# actor, or the service are resolved (they differ per app).
Identity = Callable[..., Any]  # resolves user_id (str): async on web, sync internal
ActorResolver = Callable[..., Any]  # resolves the Actor (human vs named agent)
ResumeServiceProvider = Callable[..., Any]

RESUMES_PATH = "/resumes"


def create_resumes_router(
    service_provider: ResumeServiceProvider,
    *,
    identity: Identity,
    actor: ActorResolver,
    channel: EditChannel,
) -> APIRouter:
    """Build the /resumes router, injecting the service, identity, actor, and edit channel.

    ``channel`` selects the copy-on-write scope rule for :func:`bullet_update`: the
    external app passes :attr:`EditChannel.WEB` (prompt when a bullet is shared),
    the internal app passes :attr:`EditChannel.MCP` (an explicit scope is required).
    """
    router = APIRouter(prefix=RESUMES_PATH, tags=["resumes"])

    @router.post("", status_code=201)
    async def create_resume(
        body: ResumeCreateRequest,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: ResumeService = Depends(service_provider),
    ) -> ResumeRecord:
        return await service.create(user_id, actor_, body)

    @router.get("")
    async def list_resumes(
        user_id: str = Depends(identity),
        service: ResumeService = Depends(service_provider),
        kind: ResumeKind | None = None,
        include_archived: bool = False,
    ) -> list[ResumeSummary]:
        return await service.list_resumes(user_id, kind=kind, include_archived=include_archived)

    @router.get("/{resume_id}")
    async def get_resume(
        resume_id: int,
        user_id: str = Depends(identity),
        service: ResumeService = Depends(service_provider),
    ) -> ResumeRecord:
        return await service.get(user_id, resume_id)

    @router.put("/{resume_id}")
    async def update_resume(
        resume_id: int,
        body: ResumeUpdate,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: ResumeService = Depends(service_provider),
        if_match: int = Header(alias="If-Match"),
    ) -> ResumeRecord:
        return await service.update(user_id, resume_id, actor_, if_match, body)

    @router.post("/{resume_id}/items")
    async def add_item(
        resume_id: int,
        body: AddItemRequest,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: ResumeService = Depends(service_provider),
        if_match: int = Header(alias="If-Match"),
    ) -> ResumeRecord:
        return await service.add_item(user_id, resume_id, actor_, if_match, body)

    @router.post("/{resume_id}/items/{item_id}/remove")
    async def remove_item(
        resume_id: int,
        item_id: str,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: ResumeService = Depends(service_provider),
        if_match: int = Header(alias="If-Match"),
    ) -> ResumeRecord:
        return await service.remove_item(user_id, resume_id, actor_, if_match, item_id)

    @router.post("/{resume_id}/reorder")
    async def reorder(
        resume_id: int,
        body: ResumeReorderRequest,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: ResumeService = Depends(service_provider),
        if_match: int = Header(alias="If-Match"),
    ) -> ResumeRecord:
        return await service.reorder(user_id, resume_id, actor_, if_match, body)

    @router.post("/bullet-edit")
    async def bullet_edit(
        body: ScopeEditRequest,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: ResumeService = Depends(service_provider),
    ) -> ScopeEditResult:
        return await service.bullet_update(user_id, actor_, channel, body)

    @router.post("/{resume_id}/items/{item_id}/promote")
    async def promote_item(
        resume_id: int,
        item_id: str,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: ResumeService = Depends(service_provider),
        if_match: int = Header(alias="If-Match"),
    ) -> ResumeRecord:
        return await service.promote(user_id, resume_id, actor_, if_match, item_id)

    return router
