"""Compose the resume revision dependency graph for both apps.

Binds the request-scoped render repository over ``get_session`` and injects the
process-wide object store (built once at the composition root, since it is
stateless/lazy). Both operations are reads, so the service owns no transaction and
needs no write-event publisher: the composition is simpler than the render graph.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends

from floresu.core.db import get_session
from floresu.resumes.render_repository import SqlAlchemyRenderRepository
from floresu.resumes.revision_service import ResumeRevisionService

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.storage.store import ObjectStore


def build_resume_revision_service_provider(
    object_store: ObjectStore,
) -> Callable[..., ResumeRevisionService]:
    """A FastAPI dependency that builds a request-scoped :class:`ResumeRevisionService`."""

    def provider(session: AsyncSession = Depends(get_session)) -> ResumeRevisionService:
        return ResumeRevisionService(SqlAlchemyRenderRepository(session), object_store)

    return provider
