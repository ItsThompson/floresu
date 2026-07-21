"""Compose the resume render dependency graph for both apps.

Binds the request-scoped repository and resolvers over ``get_session`` and injects
the process-wide render module and object store (built once at the composition root,
since both are stateless/lazy). The write-event publisher is read off
``app.state.events`` so an export publishes through the one seam both apps share.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends

# ``Request`` is resolved by FastAPI at runtime, so it must stay a runtime import.
from starlette.requests import Request

from floresu.core.db import get_session
from floresu.core.events import WriteEventPublisher
from floresu.resumes.identity_resolver import SqlAlchemyIdentityResolver
from floresu.resumes.render_repository import SqlAlchemyRenderRepository
from floresu.resumes.render_service import ResumeRenderService
from floresu.resumes.resolver import SqlAlchemyBulletTextResolver

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.rendering.module import RenderModule
    from floresu.storage.store import ObjectStore


def build_resume_render_service_provider(
    render_module: RenderModule, object_store: ObjectStore
) -> Callable[..., ResumeRenderService]:
    """A FastAPI dependency that builds a request-scoped :class:`ResumeRenderService`."""

    def provider(
        request: Request, session: AsyncSession = Depends(get_session)
    ) -> ResumeRenderService:
        publisher: WriteEventPublisher = request.app.state.events
        return ResumeRenderService(
            session,
            SqlAlchemyRenderRepository(session),
            SqlAlchemyBulletTextResolver(session),
            SqlAlchemyIdentityResolver(session),
            render_module,
            object_store,
            publisher,
        )

    return provider
