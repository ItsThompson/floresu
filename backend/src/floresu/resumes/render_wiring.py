"""Compose the resume render dependency graph for both apps.

Declares how a request-scoped :class:`ResumeRenderService` is built and defers the
wiring mechanics (resolving the session, reading the write-event seam) to
:func:`publishing_provider`. The ``build`` closure captures the process-wide
render module and object store (built once at the composition root, since both are
stateless/lazy), so an export publishes through the one seam both apps share.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.core.providers import ServiceProvider, publishing_provider
from floresu.resumes.identity_resolver import SqlAlchemyIdentityResolver
from floresu.resumes.render_repository import SqlAlchemyRenderRepository
from floresu.resumes.render_service import ResumeRenderService
from floresu.resumes.resolver import SqlAlchemyBulletTextResolver

if TYPE_CHECKING:
    from floresu.rendering.module import RenderModule
    from floresu.storage.store import ObjectStore


def build_resume_render_service_provider(
    render_module: RenderModule, object_store: ObjectStore
) -> ServiceProvider[ResumeRenderService]:
    """A FastAPI dependency that builds a request-scoped :class:`ResumeRenderService`."""
    return publishing_provider(
        lambda session, publisher: ResumeRenderService(
            session,
            SqlAlchemyRenderRepository(session),
            SqlAlchemyBulletTextResolver(session),
            SqlAlchemyIdentityResolver(session),
            render_module,
            object_store,
            publisher,
        )
    )
