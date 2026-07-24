"""Compose the resume finalize dependency graph for both apps.

Declares how a request-scoped :class:`ResumeFinalizeService` is built and defers
the wiring mechanics (resolving the session, reading the write-event seam) to
:func:`publishing_provider`. The shared :func:`build_resume_finalizer` constructor
is reused by the finalize route provider and by the job-application lifecycle
wiring (which injects the finalizer), so the finalize graph is defined once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.core.providers import ServiceProvider, publishing_provider
from floresu.jobapps.repository import SqlAlchemyJobApplicationRepository
from floresu.resumes.finalize import ResumeFinalizeService
from floresu.resumes.identity_resolver import SqlAlchemyIdentityResolver
from floresu.resumes.repository import SqlAlchemyResumeRepository
from floresu.resumes.resolver import SqlAlchemyBulletTextResolver

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.events import WriteEventPublisher
    from floresu.rendering.module import RenderModule
    from floresu.storage.store import ObjectStore


def build_resume_finalizer(
    session: AsyncSession,
    publisher: WriteEventPublisher,
    render_module: RenderModule,
    object_store: ObjectStore,
) -> ResumeFinalizeService:
    """Construct a request-scoped finalize service over one session (shared by both callers)."""
    return ResumeFinalizeService(
        session,
        SqlAlchemyResumeRepository(session),
        SqlAlchemyBulletTextResolver(session),
        SqlAlchemyIdentityResolver(session),
        render_module,
        object_store,
        SqlAlchemyJobApplicationRepository(session),
        publisher,
    )


def build_resume_finalize_service_provider(
    render_module: RenderModule, object_store: ObjectStore
) -> ServiceProvider[ResumeFinalizeService]:
    """A FastAPI dependency that builds a request-scoped :class:`ResumeFinalizeService`."""
    return publishing_provider(
        lambda session, publisher: build_resume_finalizer(
            session, publisher, render_module, object_store
        )
    )
