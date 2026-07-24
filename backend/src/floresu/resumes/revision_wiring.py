"""Compose the resume revision dependency graph for both apps.

Declares how a request-scoped :class:`ResumeRevisionService` is built and defers
the wiring mechanics (resolving the session) to :func:`session_provider`. Both
operations are reads, so the service owns no transaction and needs no write-event
publisher: the ``build`` closure captures only the process-wide object store.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.core.providers import ServiceProvider, session_provider
from floresu.resumes.render_repository import SqlAlchemyRenderRepository
from floresu.resumes.revision_service import ResumeRevisionService

if TYPE_CHECKING:
    from floresu.storage.store import ObjectStore


def build_resume_revision_service_provider(
    object_store: ObjectStore,
) -> ServiceProvider[ResumeRevisionService]:
    """A FastAPI dependency that builds a request-scoped :class:`ResumeRevisionService`."""
    return session_provider(
        lambda session: ResumeRevisionService(SqlAlchemyRenderRepository(session), object_store)
    )
