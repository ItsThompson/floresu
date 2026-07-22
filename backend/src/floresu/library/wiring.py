"""Compose the library dependency graph for both apps.

Keeps wiring (which request-scoped session backs the repository, where the
write-event publisher comes from) out of the router and the entrypoints. The
provider resolves a per-request ``AsyncSession`` via ``get_session``, binds the
SQLAlchemy repository over it, and reads the process-wide
:class:`WriteEventPublisher` off ``app.state.events`` (composed at the composition
root), so the service publishes every write through the one seam both apps share.

This is also where the ``library -> resumes`` boundary is bridged without a cycle:
the library declares the :class:`~floresu.library.usage.BulletUsageCounter` port and
never imports a resumes model, while this composition module binds the resumes
repository (which owns ``resume_bullet_ref`` and structurally satisfies the port) as
the counter the service reads the "used in N" count from.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends

# ``Request`` is resolved by FastAPI at runtime to inject the request object, so it
# must stay a runtime import (not TYPE_CHECKING) or it is mistaken for a field.
from starlette.requests import Request

from floresu.core.db import get_session
from floresu.core.events import WriteEventPublisher
from floresu.library.repository import SqlAlchemyLibraryRepository
from floresu.library.service import LibraryService
from floresu.resumes.repository import SqlAlchemyResumeRepository

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession


def build_bullet_service_provider() -> Callable[..., LibraryService]:
    """A FastAPI dependency that builds a request-scoped :class:`LibraryService`."""

    def provider(request: Request, session: AsyncSession = Depends(get_session)) -> LibraryService:
        publisher: WriteEventPublisher = request.app.state.events
        # The resumes repository owns resume_bullet_ref and structurally satisfies
        # BulletUsageCounter, so it is the "used in N" counter the library reads from.
        return LibraryService(
            session,
            SqlAlchemyLibraryRepository(session),
            publisher,
            SqlAlchemyResumeRepository(session),
        )

    return provider
