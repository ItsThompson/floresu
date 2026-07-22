"""Persistence for the render/export path: resume read, latest revision, PDF key.

A narrow repository the render service depends on, separate from the T12 write
repository so the rendering slice adds no methods to the single-writer's interface.
It reads the resume (user-scoped, so another account's resume is invisible), reads
the latest revision (whose number keys the object and whose ``pdf_object_key`` the
export records), and writes that object key back. It also serves the revision-history
reads: the published versions (revisions whose ``pdf_object_key`` is set) newest
first, and one revision by number. Transaction ownership stays with the service:
:meth:`set_revision_pdf_key` issues the update, but the ``transaction`` boundary the
service wraps it in is what commits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlalchemy import select, update

from floresu.core.db import fetch_optional
from floresu.resumes.models import Resume, ResumeRevision

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


class RenderRepository(Protocol):
    """Data access for rendering: the resume, its latest revision, and the PDF key."""

    async def get_resume(self, user_id: int, resume_id: int) -> Resume | None: ...

    async def latest_revision(self, resume_id: int) -> ResumeRevision | None: ...

    async def set_revision_pdf_key(
        self, resume_id: int, revision_no: int, object_key: str
    ) -> None: ...

    async def list_revisions_with_pdf(self, resume_id: int) -> Sequence[ResumeRevision]: ...

    async def get_revision(self, resume_id: int, revision_no: int) -> ResumeRevision | None: ...


class SqlAlchemyRenderRepository:
    """The production repository over a request-scoped :class:`AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_resume(self, user_id: int, resume_id: int) -> Resume | None:
        return await fetch_optional(
            self._session,
            select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id),
        )

    async def latest_revision(self, resume_id: int) -> ResumeRevision | None:
        return await fetch_optional(
            self._session,
            select(ResumeRevision)
            .where(ResumeRevision.resume_id == resume_id)
            .order_by(ResumeRevision.revision_no.desc())
            .limit(1),
        )

    async def set_revision_pdf_key(self, resume_id: int, revision_no: int, object_key: str) -> None:
        await self._session.execute(
            update(ResumeRevision)
            .where(
                ResumeRevision.resume_id == resume_id,
                ResumeRevision.revision_no == revision_no,
            )
            .values(pdf_object_key=object_key)
        )

    async def list_revisions_with_pdf(self, resume_id: int) -> Sequence[ResumeRevision]:
        result = await self._session.execute(
            select(ResumeRevision)
            .where(
                ResumeRevision.resume_id == resume_id,
                ResumeRevision.pdf_object_key.is_not(None),
            )
            .order_by(ResumeRevision.revision_no.desc())
        )
        return result.scalars().all()

    async def get_revision(self, resume_id: int, revision_no: int) -> ResumeRevision | None:
        return await fetch_optional(
            self._session,
            select(ResumeRevision).where(
                ResumeRevision.resume_id == resume_id,
                ResumeRevision.revision_no == revision_no,
            ),
        )
