"""Compose the worklog dependency graph for both apps.

Declares how a request-scoped :class:`WorklogService` is built and defers the
wiring mechanics (resolving the session, reading the write-event seam) to
:func:`publishing_provider`, so every write publishes through the one seam both
apps share.
"""

from __future__ import annotations

from floresu.core.providers import ServiceProvider, publishing_provider
from floresu.worklog.repository import SqlAlchemyWorklogRepository
from floresu.worklog.service import WorklogService


def build_worklog_service_provider() -> ServiceProvider[WorklogService]:
    """A FastAPI dependency that builds a request-scoped :class:`WorklogService`."""
    return publishing_provider(
        lambda session, publisher: WorklogService(
            session, SqlAlchemyWorklogRepository(session), publisher
        )
    )
