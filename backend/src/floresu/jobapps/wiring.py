"""Compose the job-application dependency graph for both apps.

Declares how a request-scoped :class:`JobApplicationService` is built and defers
the wiring mechanics (resolving the session, reading the write-event seam) to
:func:`publishing_provider`. The ``build`` closure captures the process-wide
render module and object store, needed to build the finalizer the submit trigger
delegates to. The finalizer is built with the same shared constructor the finalize
route uses, so the submit=finalize path and the direct finalize path run identical
logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.core.providers import ServiceProvider, publishing_provider
from floresu.jobapps.repository import SqlAlchemyJobApplicationRepository
from floresu.jobapps.service import JobApplicationService
from floresu.resumes.finalize_wiring import build_resume_finalizer

if TYPE_CHECKING:
    from floresu.rendering.module import RenderModule
    from floresu.storage.store import ObjectStore


def build_jobapps_service_provider(
    render_module: RenderModule, object_store: ObjectStore
) -> ServiceProvider[JobApplicationService]:
    """A FastAPI dependency that builds a request-scoped :class:`JobApplicationService`."""
    return publishing_provider(
        lambda session, publisher: JobApplicationService(
            session,
            SqlAlchemyJobApplicationRepository(session),
            publisher,
            build_resume_finalizer(session, publisher, render_module, object_store),
        )
    )
