"""HTTP adapter for the resume finalize action, mounted on both apps.

A single thin handler over :class:`ResumeFinalizeService`: finalize the application
draft (freeze references to inline read-only text, snapshot the identity, render and
store the frozen PDF, submit a linked job application). The external app injects the
cookie identity and a human actor; the internal app injects the trusted-header
identity and the named-agent actor. Business rules, the transaction, the object-store
write, and the write-event publish live in the service.

The path (``/resumes/{resume_id}/finalize``) carries a suffix, so it never collides
with the resumes router's ``/resumes/{resume_id}`` read; mounting order is irrelevant.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from floresu.core.actor import Actor
from floresu.core.providers import ActorResolver, Identity, ServiceProvider
from floresu.resumes.finalize import ResumeFinalizeService
from floresu.resumes.schemas import FinalizeResult

RESUMES_PATH = "/resumes"


def create_resume_finalize_router(
    service_provider: ServiceProvider[ResumeFinalizeService],
    *,
    identity: Identity,
    actor: ActorResolver,
) -> APIRouter:
    """Build the resume finalize router, injecting the service, identity, and actor."""
    router = APIRouter(prefix=RESUMES_PATH, tags=["resumes"])

    @router.post("/{resume_id}/finalize")
    async def finalize_resume(
        resume_id: int,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: ResumeFinalizeService = Depends(service_provider),
    ) -> FinalizeResult:
        return await service.finalize(user_id, resume_id, actor_)

    return router
