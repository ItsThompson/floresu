"""Compose the resume dependency graph for both apps.

Keeps wiring (which request-scoped session backs the repository and the resolver,
where the write-event publisher comes from) out of the router and the entrypoints.
The provider resolves a per-request ``AsyncSession`` via ``get_session``, binds the
SQLAlchemy repository and the bullet-text resolver over it, and reads the
process-wide :class:`WriteEventPublisher` off ``app.state.events`` (composed at the
composition root), so the service publishes every write through the one seam both
apps share.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends

# ``Request`` is resolved by FastAPI at runtime to inject the request object, so it
# must stay a runtime import (not TYPE_CHECKING) or it is mistaken for a field.
from starlette.requests import Request

from floresu.core.db import get_session
from floresu.core.events import WriteEventPublisher
from floresu.library.cow import LibraryCanonicalBulletWriter
from floresu.library.repository import SqlAlchemyLibraryRepository
from floresu.resumes.repository import SqlAlchemyResumeRepository
from floresu.resumes.resolver import SqlAlchemyBulletTextResolver
from floresu.resumes.service import ResumeService

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession


def build_resume_service_provider() -> Callable[..., ResumeService]:
    """A FastAPI dependency that builds a request-scoped :class:`ResumeService`."""

    def provider(request: Request, session: AsyncSession = Depends(get_session)) -> ResumeService:
        publisher: WriteEventPublisher = request.app.state.events
        return ResumeService(
            session,
            SqlAlchemyResumeRepository(session),
            SqlAlchemyBulletTextResolver(session),
            publisher,
            LibraryCanonicalBulletWriter(session, SqlAlchemyLibraryRepository(session), publisher),
        )

    return provider
