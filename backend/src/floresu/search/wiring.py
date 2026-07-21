"""Compose the search dependency graph for both apps.

Keeps wiring (which request-scoped session backs the repository, which embedding
provider embeds the query) out of the router and the entrypoints. The provider
resolves a per-request :class:`~sqlalchemy.ext.asyncio.AsyncSession` via
``get_session``, binds the SQLAlchemy retrieval repository over it, and closes
over the process-wide embedding provider (the one built at each composition root),
so both apps share one :class:`SearchService` shape and only the injected provider
and identity differ.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends

from floresu.core.db import get_session
from floresu.search.retrieval import SqlAlchemySearchRepository
from floresu.search.service import SearchService

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.embedding.provider import EmbeddingProvider


def build_search_service_provider(
    provider: EmbeddingProvider,
) -> Callable[..., SearchService]:
    """A FastAPI dependency that builds a request-scoped :class:`SearchService`."""

    def build(session: AsyncSession = Depends(get_session)) -> SearchService:
        return SearchService(SqlAlchemySearchRepository(session), provider)

    return build
