"""Job application persistence: the repository interface and its SQLAlchemy binding.

The single home for ``job_applications`` data access, used by the lifecycle service
and by the finalize routine (which reads and marks a linked application submitted).
Every read is scoped to ``user_id`` so another account's application is invisible
(the service turns a miss into a 404). The 1:1 resume link lives on
``resumes.job_application_id``, so resolving "the linked resume" is a scoped read of
that column rather than a second source of truth.

Transaction ownership stays with the service: :meth:`add` flushes to mint the id and
status mutations flow through the session the service commits; the ``transaction``
boundary the service (or finalize) wraps its write in is what commits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlalchemy import select

from floresu.core.db import fetch_optional
from floresu.resumes.models import JobApplication, Resume

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


class JobApplicationRepository(Protocol):
    """Data access for job applications and their 1:1 resume link."""

    async def add(self, application: JobApplication) -> None: ...

    async def get(self, user_id: int, application_id: int) -> JobApplication | None: ...

    async def list_applications(self, user_id: int, *, limit: int) -> Sequence[JobApplication]: ...

    async def linked_resume_id(self, application_id: int) -> int | None: ...

    async def linked_resume_ids(self, application_ids: Sequence[int]) -> dict[int, int]: ...


class SqlAlchemyJobApplicationRepository:
    """The production repository over a request-scoped :class:`AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, application: JobApplication) -> None:
        self._session.add(application)
        # Flush so the identity id is minted for the read-back projection.
        await self._session.flush()

    async def get(self, user_id: int, application_id: int) -> JobApplication | None:
        return await fetch_optional(
            self._session,
            select(JobApplication).where(
                JobApplication.id == application_id, JobApplication.user_id == user_id
            ),
        )

    async def list_applications(self, user_id: int, *, limit: int) -> Sequence[JobApplication]:
        result = await self._session.execute(
            select(JobApplication)
            .where(JobApplication.user_id == user_id)
            .order_by(JobApplication.id.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def linked_resume_id(self, application_id: int) -> int | None:
        return await fetch_optional(
            self._session,
            select(Resume.id).where(Resume.job_application_id == application_id),
        )

    async def linked_resume_ids(self, application_ids: Sequence[int]) -> dict[int, int]:
        if not application_ids:
            return {}
        result = await self._session.execute(
            select(Resume.job_application_id, Resume.id).where(
                Resume.job_application_id.in_(application_ids)
            )
        )
        return {
            application_id: resume_id
            for application_id, resume_id in result.all()
            if application_id is not None
        }
