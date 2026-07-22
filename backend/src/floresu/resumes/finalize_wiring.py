"""Compose the resume finalize dependency graph for both apps.

Binds the request-scoped repositories and resolvers over ``get_session`` and injects
the process-wide render module and object store (built once at the composition root).
The write-event publisher is read off ``app.state.events`` so finalize publishes
through the one seam both apps share. The shared :func:`build_resume_finalizer`
constructor is reused by the finalize route provider and by the job-application
lifecycle wiring (which injects the finalizer), so the finalize graph is defined once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends

# ``Request`` is resolved by FastAPI at runtime, so it must stay a runtime import.
from starlette.requests import Request

from floresu.core.db import get_session
from floresu.core.events import WriteEventPublisher
from floresu.jobapps.repository import SqlAlchemyJobApplicationRepository
from floresu.resumes.finalize import ResumeFinalizeService
from floresu.resumes.identity_resolver import SqlAlchemyIdentityResolver
from floresu.resumes.repository import SqlAlchemyResumeRepository
from floresu.resumes.resolver import SqlAlchemyBulletTextResolver

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

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
) -> Callable[..., ResumeFinalizeService]:
    """A FastAPI dependency that builds a request-scoped :class:`ResumeFinalizeService`."""

    def provider(
        request: Request, session: AsyncSession = Depends(get_session)
    ) -> ResumeFinalizeService:
        publisher: WriteEventPublisher = request.app.state.events
        return build_resume_finalizer(session, publisher, render_module, object_store)

    return provider
