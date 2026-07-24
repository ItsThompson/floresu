"""Compose the library dependency graph for both apps.

Declares how a request-scoped :class:`LibraryService` is built and defers the
wiring mechanics (resolving the session, reading the write-event seam) to
:func:`publishing_provider`, so every write publishes through the one seam both
apps share.

This is also where the ``library -> resumes`` boundary is bridged without a cycle:
the library declares the :class:`~floresu.library.usage.BulletUsageCounter` port and
never imports a resumes model, while this composition module binds the resumes
repository (which owns ``resume_bullet_ref`` and structurally satisfies the port) as
the counter the service reads the "used in N" count from.
"""

from __future__ import annotations

from floresu.core.providers import ServiceProvider, publishing_provider
from floresu.library.repository import SqlAlchemyLibraryRepository
from floresu.library.service import LibraryService
from floresu.resumes.repository import SqlAlchemyResumeRepository


def build_bullet_service_provider() -> ServiceProvider[LibraryService]:
    """A FastAPI dependency that builds a request-scoped :class:`LibraryService`."""
    # The resumes repository owns resume_bullet_ref and structurally satisfies
    # BulletUsageCounter, so it is the "used in N" counter the library reads from.
    return publishing_provider(
        lambda session, publisher: LibraryService(
            session,
            SqlAlchemyLibraryRepository(session),
            publisher,
            SqlAlchemyResumeRepository(session),
        )
    )
