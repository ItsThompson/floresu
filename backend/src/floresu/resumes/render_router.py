"""HTTP adapter for resume rendering, mounted on both apps with per-boundary identity.

Thin handlers over :class:`ResumeRenderService`: list the global templates, stream an
ephemeral preview PDF (never stored), and export (render, persist to R2, record the
object key, return a time-limited download URL). The external app injects the cookie
identity and a human actor; the internal app injects the trusted-header identity and
the named-agent actor. Business rules, resolution, the object-store write, and the
write-event publish all live in the service.

This router is mounted *before* the resumes router so its static ``/resumes/templates``
route is matched ahead of the resumes router's ``/resumes/{resume_id}`` route.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Response

from floresu.core.actor import Actor
from floresu.rendering.config import PDF_MEDIA_TYPE
from floresu.rendering.schemas import TemplateInfo
from floresu.resumes.render_schemas import ExportResult, PreviewRequest
from floresu.resumes.render_service import ResumeRenderService

# Injected so the router never hard-codes how identity, the actor, or the service
# are resolved (they differ per app), mirroring the resumes router.
Identity = Callable[..., Any]
ActorResolver = Callable[..., Any]
ResumeRenderServiceProvider = Callable[..., Any]

RESUMES_PATH = "/resumes"


def create_resume_render_router(
    service_provider: ResumeRenderServiceProvider,
    *,
    identity: Identity,
    actor: ActorResolver,
) -> APIRouter:
    """Build the resume render router, injecting the service, identity, and actor."""
    router = APIRouter(prefix=RESUMES_PATH, tags=["resumes"])

    @router.get("/templates")
    async def list_templates(
        _user_id: str = Depends(identity),
        service: ResumeRenderService = Depends(service_provider),
    ) -> list[TemplateInfo]:
        return service.list_templates()

    @router.post("/{resume_id}/preview")
    async def preview_resume(
        resume_id: int,
        body: PreviewRequest | None = None,
        user_id: str = Depends(identity),
        service: ResumeRenderService = Depends(service_provider),
    ) -> Response:
        template_id = body.template_id if body is not None else None
        pdf = await service.preview(user_id, resume_id, template_id)
        return Response(content=pdf, media_type=PDF_MEDIA_TYPE)

    @router.post("/{resume_id}/export")
    async def export_resume(
        resume_id: int,
        user_id: str = Depends(identity),
        actor_: Actor = Depends(actor),
        service: ResumeRenderService = Depends(service_provider),
    ) -> ExportResult:
        return await service.export(user_id, resume_id, actor_)

    return router
