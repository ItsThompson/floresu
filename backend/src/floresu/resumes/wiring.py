"""Compose the resume dependency graph for both apps.

Declares how a request-scoped :class:`ResumeService` is built and defers the
wiring mechanics (resolving the session, reading the write-event seam) to
:func:`publishing_provider`. Binds the SQLAlchemy repository and the bullet-text
resolver over the one session, so the service publishes every write through the
one seam both apps share.
"""

from __future__ import annotations

from floresu.core.providers import ServiceProvider, publishing_provider
from floresu.library.cow import LibraryCanonicalBulletWriter
from floresu.library.repository import SqlAlchemyLibraryRepository
from floresu.resumes.repository import SqlAlchemyResumeRepository
from floresu.resumes.resolver import SqlAlchemyBulletTextResolver
from floresu.resumes.service import ResumeService


def build_resume_service_provider() -> ServiceProvider[ResumeService]:
    """A FastAPI dependency that builds a request-scoped :class:`ResumeService`."""
    return publishing_provider(
        lambda session, publisher: ResumeService(
            session,
            SqlAlchemyResumeRepository(session),
            SqlAlchemyBulletTextResolver(session),
            publisher,
            LibraryCanonicalBulletWriter(session, SqlAlchemyLibraryRepository(session), publisher),
        )
    )
