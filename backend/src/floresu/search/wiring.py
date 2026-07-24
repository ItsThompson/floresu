"""Compose the search dependency graph for both apps.

Declares how a request-scoped :class:`SearchService` is built and defers the
wiring mechanics (resolving the session) to :func:`session_provider`. The
``build`` closure captures the process-wide embedding provider (built at each
composition root), so both apps share one :class:`SearchService` shape and only
the injected provider and identity differ.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.core.providers import ServiceProvider, session_provider
from floresu.search.retrieval import SqlAlchemySearchRepository
from floresu.search.service import SearchService

if TYPE_CHECKING:
    from floresu.embedding.provider import EmbeddingProvider


def build_search_service_provider(
    provider: EmbeddingProvider,
) -> ServiceProvider[SearchService]:
    """A FastAPI dependency that builds a request-scoped :class:`SearchService`."""
    return session_provider(
        lambda session: SearchService(SqlAlchemySearchRepository(session), provider)
    )
