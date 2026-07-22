"""HTTP adapter for resume revision history, mounted on both apps with per-boundary identity.

Thin handlers over :class:`ResumeRevisionService`: list a resume's published versions
(revisions with a stored PDF) and mint a presigned URL for one version's stored PDF.
The external app injects the cookie identity; the internal app injects the
trusted-header identity. Both are reads: neither carries an actor nor publishes a
write event. Ownership and the missing-version 404 live in the service.

The two paths carry a ``/revisions`` segment, so they never collide with the resumes
router's ``/resumes/{resume_id}`` read regardless of mount order; grouping them with
the render router is for cohesion only.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends

from floresu.resumes.revision_schemas import PublishedVersionList, VersionPdfUrl
from floresu.resumes.revision_service import ResumeRevisionService

# Injected so the router never hard-codes how identity or the service are resolved
# (they differ per app), mirroring the resume render router.
Identity = Callable[..., Any]
ResumeRevisionServiceProvider = Callable[..., Any]

RESUMES_PATH = "/resumes"


def create_resume_revision_router(
    service_provider: ResumeRevisionServiceProvider,
    *,
    identity: Identity,
) -> APIRouter:
    """Build the resume revision router, injecting the service and identity."""
    router = APIRouter(prefix=RESUMES_PATH, tags=["resumes"])

    @router.get("/{resume_id}/revisions")
    async def list_revisions(
        resume_id: int,
        user_id: str = Depends(identity),
        service: ResumeRevisionService = Depends(service_provider),
    ) -> PublishedVersionList:
        return await service.list_published_versions(user_id, resume_id)

    @router.get("/{resume_id}/revisions/{revision_no}/pdf")
    async def revision_pdf(
        resume_id: int,
        revision_no: int,
        user_id: str = Depends(identity),
        service: ResumeRevisionService = Depends(service_provider),
    ) -> VersionPdfUrl:
        return await service.version_pdf_url(user_id, resume_id, revision_no)

    return router
