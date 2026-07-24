"""HTTP adapter for job applications, mounted on both apps with per-boundary identity.

Thin handlers: each resolves the caller's ``user_id`` and :class:`Actor` through
injected dependencies and calls exactly one :class:`JobApplicationService` method.
The external app injects the cookie identity and a human actor; the internal app
injects the trusted-header identity and the named-agent actor. Business rules, the
transaction, the submit=finalize convergence, and the write-event publish live in
the service, so both boundaries share one implementation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from floresu.core.actor import Actor
from floresu.core.providers import ActorResolver, Identity, ServiceProvider
from floresu.jobapps.schemas import (
    JobApplicationCreate,
    JobApplicationSummary,
    JobApplicationUpdate,
)
from floresu.jobapps.service import JobApplicationService

JOB_APPLICATIONS_PATH = "/job-applications"


def create_jobapps_router(
    service_provider: ServiceProvider[JobApplicationService],
    *,
    identity: Identity,
    actor: ActorResolver,
) -> APIRouter:
    """Build the /job-applications router, injecting the service, identity, and actor."""
    router = APIRouter(prefix=JOB_APPLICATIONS_PATH, tags=["job-applications"])

    @router.post("", status_code=201)
    async def create_application(
        body: JobApplicationCreate,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: JobApplicationService = Depends(service_provider),
    ) -> JobApplicationSummary:
        return await service.create(user_id, actor_, body)

    @router.get("")
    async def list_applications(
        user_id: str = Depends(identity),
        service: JobApplicationService = Depends(service_provider),
    ) -> list[JobApplicationSummary]:
        return await service.list_applications(user_id)

    @router.get("/{application_id}")
    async def get_application(
        application_id: int,
        user_id: str = Depends(identity),
        service: JobApplicationService = Depends(service_provider),
    ) -> JobApplicationSummary:
        return await service.get(user_id, application_id)

    @router.patch("/{application_id}")
    async def update_application(
        application_id: int,
        body: JobApplicationUpdate,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: JobApplicationService = Depends(service_provider),
    ) -> JobApplicationSummary:
        return await service.update(user_id, actor_, application_id, body)

    return router
