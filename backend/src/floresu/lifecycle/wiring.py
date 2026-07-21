"""Compose the lifecycle dependency graph for the external app.

Keeps wiring (which request-scoped session backs the repositories, where the
write-event publisher comes from) out of the router and the entrypoint. The
provider resolves a per-request ``AsyncSession`` via ``get_session``, binds the
destructive repository, the read-only export repository, and the shared embedding
repository over it (so the vector purge enlists in the same transaction as the
hard delete), and reads the process-wide :class:`WriteEventPublisher` off
``app.state.events``. This service is only ever wired on the external app.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends

# ``Request`` is resolved by FastAPI at runtime to inject the request object, so it
# must stay a runtime import (not TYPE_CHECKING) or it is mistaken for a field.
from starlette.requests import Request

from floresu.core.db import get_session
from floresu.core.events import WriteEventPublisher
from floresu.embedding.repository import SqlAlchemyEmbeddingRepository
from floresu.lifecycle.export_repository import SqlAlchemyExportRepository
from floresu.lifecycle.repository import SqlAlchemyLifecycleRepository
from floresu.lifecycle.service import LifecycleService

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession


def build_lifecycle_service_provider() -> Callable[..., LifecycleService]:
    """A FastAPI dependency that builds a request-scoped :class:`LifecycleService`."""

    def provider(
        request: Request, session: AsyncSession = Depends(get_session)
    ) -> LifecycleService:
        publisher: WriteEventPublisher = request.app.state.events
        return LifecycleService(
            session,
            SqlAlchemyLifecycleRepository(session),
            SqlAlchemyExportRepository(session),
            SqlAlchemyEmbeddingRepository(session),
            publisher,
        )

    return provider
