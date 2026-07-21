"""Compose the job-application dependency graph for both apps.

Binds the request-scoped repository over ``get_session`` and injects the process-wide
render module and object store (needed to build the finalizer the submit trigger
delegates to). The write-event publisher is read off ``app.state.events`` so every
job-application write publishes through the one seam both apps share. The finalizer is
built with the same shared constructor the finalize route uses, so the submit=finalize
path and the direct finalize path run identical logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends

# ``Request`` is resolved by FastAPI at runtime, so it must stay a runtime import.
from starlette.requests import Request

from floresu.core.db import get_session
from floresu.core.events import WriteEventPublisher
from floresu.jobapps.repository import SqlAlchemyJobApplicationRepository
from floresu.jobapps.service import JobApplicationService
from floresu.resumes.finalize_wiring import build_resume_finalizer

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.rendering.module import RenderModule
    from floresu.storage.store import ObjectStore


def build_jobapps_service_provider(
    render_module: RenderModule, object_store: ObjectStore
) -> Callable[..., JobApplicationService]:
    """A FastAPI dependency that builds a request-scoped :class:`JobApplicationService`."""

    def provider(
        request: Request, session: AsyncSession = Depends(get_session)
    ) -> JobApplicationService:
        publisher: WriteEventPublisher = request.app.state.events
        finalizer = build_resume_finalizer(session, publisher, render_module, object_store)
        return JobApplicationService(
            session,
            SqlAlchemyJobApplicationRepository(session),
            publisher,
            finalizer,
        )

    return provider
