"""HTTP adapter for skills, mounted on both apps with per-boundary identity.

Thin handlers: each resolves the caller's ``user_id`` and :class:`Actor` through
injected dependencies and calls exactly one :class:`SkillService` method. The
external app injects the cookie identity and a human actor; the internal app
injects the trusted-header identity and the named-agent actor. Business rules, the
transaction, and the write-event publish all live in the service, so both
boundaries share one implementation and provenance is uniform.

Skills carry a reorder (unlike identity variants), so ``POST /skills/reorder`` is
declared before ``/skills/{skill_id}`` so the literal path is matched ahead of the
id parameter.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from floresu.core.actor import Actor
from floresu.core.providers import ActorResolver, Identity, ServiceProvider
from floresu.profile.skills.schemas import SkillRead, SkillReorderRequest, SkillWrite
from floresu.profile.skills.service import SkillService

SKILLS_PATH = "/skills"


def create_skills_router(
    service_provider: ServiceProvider[SkillService],
    *,
    identity: Identity,
    actor: ActorResolver,
) -> APIRouter:
    """Build the /skills router, injecting the service, identity, and actor."""
    router = APIRouter(prefix=SKILLS_PATH, tags=["skills"])

    @router.post("", status_code=201)
    async def create_skill(
        body: SkillWrite,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: SkillService = Depends(service_provider),
    ) -> SkillRead:
        return await service.create(user_id, actor_, body)

    @router.get("")
    async def list_skills(
        user_id: str = Depends(identity),
        service: SkillService = Depends(service_provider),
        include_archived: bool = False,
    ) -> list[SkillRead]:
        return await service.list_skills(user_id, include_archived=include_archived)

    @router.post("/reorder")
    async def reorder_skills(
        body: SkillReorderRequest,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: SkillService = Depends(service_provider),
    ) -> list[SkillRead]:
        return await service.reorder(user_id, actor_, body)

    @router.get("/{skill_id}")
    async def get_skill(
        skill_id: int,
        user_id: str = Depends(identity),
        service: SkillService = Depends(service_provider),
    ) -> SkillRead:
        return await service.get(user_id, skill_id)

    @router.put("/{skill_id}")
    async def update_skill(
        skill_id: int,
        body: SkillWrite,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: SkillService = Depends(service_provider),
    ) -> SkillRead:
        return await service.update(user_id, skill_id, actor_, body)

    @router.post("/{skill_id}/archive")
    async def archive_skill(
        skill_id: int,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: SkillService = Depends(service_provider),
    ) -> SkillRead:
        return await service.archive(user_id, skill_id, actor_)

    @router.post("/{skill_id}/restore")
    async def restore_skill(
        skill_id: int,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: SkillService = Depends(service_provider),
    ) -> SkillRead:
        return await service.restore(user_id, skill_id, actor_)

    return router
