"""Compose the identity-variant dependency graph for both apps.

Keeps wiring (which request-scoped session backs the repository, where the
write-event publisher comes from) out of the router and the entrypoints. The
provider resolves a per-request ``AsyncSession`` via ``get_session``, binds the
SQLAlchemy repository over it, and reads the process-wide
:class:`WriteEventPublisher` off ``app.state.events``, so the service publishes
every write through the one seam both apps share.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends

# ``Request`` is resolved by FastAPI at runtime to inject the request object, so it
# must stay a runtime import (not TYPE_CHECKING) or it is mistaken for a field.
from starlette.requests import Request

from floresu.core.db import get_session
from floresu.core.events import WriteEventPublisher
from floresu.profile.variants.repository import SqlAlchemyIdentityVariantRepository
from floresu.profile.variants.service import IdentityVariantService

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession


def build_variant_service_provider() -> Callable[..., IdentityVariantService]:
    """A FastAPI dependency that builds a request-scoped :class:`IdentityVariantService`."""

    def provider(
        request: Request, session: AsyncSession = Depends(get_session)
    ) -> IdentityVariantService:
        publisher: WriteEventPublisher = request.app.state.events
        return IdentityVariantService(
            session, SqlAlchemyIdentityVariantRepository(session), publisher
        )

    return provider
