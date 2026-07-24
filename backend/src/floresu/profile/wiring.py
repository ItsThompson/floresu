"""Compose the sources dependency graph for both apps.

Declares how a request-scoped :class:`SourceService` is built and defers the
wiring mechanics (resolving the session, reading the write-event seam) to
:func:`publishing_provider`, so every write publishes through the one seam both
apps share.
"""

from __future__ import annotations

from floresu.core.providers import ServiceProvider, publishing_provider
from floresu.profile.repository import SqlAlchemySourceRepository
from floresu.profile.service import SourceService


def build_source_service_provider() -> ServiceProvider[SourceService]:
    """A FastAPI dependency that builds a request-scoped :class:`SourceService`."""
    return publishing_provider(
        lambda session, publisher: SourceService(
            session, SqlAlchemySourceRepository(session), publisher
        )
    )
