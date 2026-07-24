"""Compose the lifecycle dependency graph for the external app.

Declares how a request-scoped :class:`LifecycleService` is built and defers the
wiring mechanics (resolving the session, reading the write-event seam) to
:func:`publishing_provider`. Binds the destructive repository, the read-only
export repository, and the shared embedding repository over the one session, so
the vector purge enlists in the same transaction as the hard delete. This service
is only ever wired on the external app.
"""

from __future__ import annotations

from floresu.core.providers import ServiceProvider, publishing_provider
from floresu.embedding.repository import SqlAlchemyEmbeddingRepository
from floresu.lifecycle.export_repository import SqlAlchemyExportRepository
from floresu.lifecycle.repository import SqlAlchemyLifecycleRepository
from floresu.lifecycle.service import LifecycleService


def build_lifecycle_service_provider() -> ServiceProvider[LifecycleService]:
    """A FastAPI dependency that builds a request-scoped :class:`LifecycleService`."""
    return publishing_provider(
        lambda session, publisher: LifecycleService(
            session,
            SqlAlchemyLifecycleRepository(session),
            SqlAlchemyExportRepository(session),
            SqlAlchemyEmbeddingRepository(session),
            publisher,
        )
    )
