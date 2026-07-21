"""HTTP adapter for identity variants, mounted on both apps with per-boundary identity.

Thin handlers: each resolves the caller's ``user_id`` and :class:`Actor` through
injected dependencies and calls exactly one :class:`IdentityVariantService` method.
The external app injects the cookie identity and a human actor; the internal app
injects the trusted-header identity and the named-agent actor. Business rules, the
transaction, and the write-event publish all live in the service, so both
boundaries share one implementation and provenance is uniform.

Identity variants are unordered, so this router deliberately exposes no reorder
operation: the default is set via ``PUT`` (``is_default``), matching the profile
family table where reorder is valid for sources and skills but not variants.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends

from floresu.core.actor import Actor
from floresu.profile.variants.schemas import IdentityVariantRead, IdentityVariantWrite
from floresu.profile.variants.service import IdentityVariantService

# FastAPI dependencies, injected so the router never hard-codes how identity, the
# actor, or the service are resolved (they differ per app).
Identity = Callable[..., Any]  # resolves user_id (str): async on web, sync internal
ActorResolver = Callable[..., Any]  # resolves the Actor (human vs named agent)
IdentityVariantServiceProvider = Callable[..., Any]

VARIANTS_PATH = "/identity-variants"


def create_variants_router(
    service_provider: IdentityVariantServiceProvider,
    *,
    identity: Identity,
    actor: ActorResolver,
) -> APIRouter:
    """Build the /identity-variants router, injecting the service, identity, and actor."""
    router = APIRouter(prefix=VARIANTS_PATH, tags=["identity-variants"])

    @router.post("", status_code=201)
    async def create_variant(
        body: IdentityVariantWrite,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: IdentityVariantService = Depends(service_provider),
    ) -> IdentityVariantRead:
        return await service.create(user_id, actor_, body)

    @router.get("")
    async def list_variants(
        user_id: str = Depends(identity),
        service: IdentityVariantService = Depends(service_provider),
        include_archived: bool = False,
    ) -> list[IdentityVariantRead]:
        return await service.list_variants(user_id, include_archived=include_archived)

    @router.get("/{variant_id}")
    async def get_variant(
        variant_id: int,
        user_id: str = Depends(identity),
        service: IdentityVariantService = Depends(service_provider),
    ) -> IdentityVariantRead:
        return await service.get(user_id, variant_id)

    @router.put("/{variant_id}")
    async def update_variant(
        variant_id: int,
        body: IdentityVariantWrite,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: IdentityVariantService = Depends(service_provider),
    ) -> IdentityVariantRead:
        return await service.update(user_id, variant_id, actor_, body)

    @router.post("/{variant_id}/archive")
    async def archive_variant(
        variant_id: int,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: IdentityVariantService = Depends(service_provider),
    ) -> IdentityVariantRead:
        return await service.archive(user_id, variant_id, actor_)

    @router.post("/{variant_id}/restore")
    async def restore_variant(
        variant_id: int,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: IdentityVariantService = Depends(service_provider),
    ) -> IdentityVariantRead:
        return await service.restore(user_id, variant_id, actor_)

    return router
