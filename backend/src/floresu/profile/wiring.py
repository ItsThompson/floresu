"""Compose the sources dependency graph for both apps.

Keeps wiring (which request-scoped session backs the repository, where the
write-event publisher comes from) out of the router and the entrypoints. The
provider resolves a per-request ``AsyncSession`` via ``get_session``, binds the
SQLAlchemy repository over it, and reads the process-wide
:class:`WriteEventPublisher` off ``app.state.events`` (composed at the composition
root), so the service publishes every write through the one seam both apps share.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends

# ``Request`` is resolved by FastAPI at runtime to inject the request object, so it
# must stay a runtime import (not TYPE_CHECKING) or it is mistaken for a field.
from starlette.requests import Request

from floresu.core.db import get_session
from floresu.core.events import WriteEventPublisher
from floresu.profile.repository import SqlAlchemySourceRepository
from floresu.profile.service import SourceService

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession


def build_source_service_provider() -> Callable[..., SourceService]:
    """A FastAPI dependency that builds a request-scoped :class:`SourceService`."""

    def provider(request: Request, session: AsyncSession = Depends(get_session)) -> SourceService:
        publisher: WriteEventPublisher = request.app.state.events
        return SourceService(session, SqlAlchemySourceRepository(session), publisher)

    return provider
