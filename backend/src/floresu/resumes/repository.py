"""Resume persistence: the repository interface and its SQLAlchemy binding.

The service depends on the :class:`ResumeRepository` interface and receives a
resolved integer ``user_id``; tests substitute an in-memory repository while
production binds :class:`SqlAlchemyResumeRepository` over a request-scoped
``AsyncSession``. Every resume read is scoped to ``user_id`` so another account's
row is invisible (the service turns a miss into a 404, never a cross-account
leak). Job-application ownership is checked through :meth:`owned_job_application_ids`
so an application resume can never link a foreign job application.
:meth:`ids_referencing_variant` is the read the identity-variant archive flow keys
on: the ids of a user's living resumes whose header references a given variant, so
the variants domain can re-point them without importing a resumes model.

Transaction ownership stays with the service: :meth:`add` flushes to mint the
resume id the revision and bullet-ref rows need, :meth:`set_bullet_refs` replaces
the write-derived index for a resume, and :meth:`add_revision` appends one keep-all
snapshot, but the ``transaction`` boundary the service wraps its write in is what
commits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlalchemy import delete, func, select

from floresu.core.db import fetch_optional, owned_ids
from floresu.resumes.models import (
    JobApplication,
    Resume,
    ResumeBulletRef,
    ResumeKind,
    ResumeRevision,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


class ResumeRepository(Protocol):
    """Data access for resumes, their write-derived bullet index, and their revisions."""

    async def add(self, resume: Resume) -> None: ...

    async def get(self, user_id: int, resume_id: int) -> Resume | None: ...

    async def list_resumes(
        self, user_id: int, *, kind: ResumeKind | None, include_archived: bool, limit: int
    ) -> Sequence[Resume]: ...

    async def owned_job_application_ids(
        self, user_id: int, job_application_ids: Sequence[int]
    ) -> set[int]: ...

    async def job_application_link_exists(self, job_application_id: int) -> bool: ...

    async def set_bullet_refs(self, resume_id: int, bullet_ids: Sequence[int]) -> None: ...

    async def add_revision(self, revision: ResumeRevision) -> None: ...

    async def ids_referencing_variant(self, user_id: int, variant_id: int) -> Sequence[int]: ...

    async def used_in_count(self, bullet_id: int) -> int: ...

    async def used_in_counts(self, bullet_ids: Sequence[int]) -> dict[int, int]: ...


class SqlAlchemyResumeRepository:
    """The production repository over a request-scoped :class:`AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, resume: Resume) -> None:
        self._session.add(resume)
        # Flush so the identity id is minted; the revision + bullet-ref rows need it.
        await self._session.flush()

    async def get(self, user_id: int, resume_id: int) -> Resume | None:
        return await fetch_optional(
            self._session,
            select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id),
        )

    async def list_resumes(
        self, user_id: int, *, kind: ResumeKind | None, include_archived: bool, limit: int
    ) -> Sequence[Resume]:
        statement = select(Resume).where(Resume.user_id == user_id)
        if kind is not None:
            statement = statement.where(Resume.kind == kind)
        if not include_archived:
            statement = statement.where(Resume.archived_at.is_(None))
        statement = statement.order_by(Resume.id.desc()).limit(limit)
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def owned_job_application_ids(
        self, user_id: int, job_application_ids: Sequence[int]
    ) -> set[int]:
        return await owned_ids(
            self._session,
            user_pk_column=JobApplication.user_id,
            id_column=JobApplication.id,
            user_pk=user_id,
            candidate_ids=job_application_ids,
        )

    async def job_application_link_exists(self, job_application_id: int) -> bool:
        existing = await fetch_optional(
            self._session,
            select(Resume.id).where(Resume.job_application_id == job_application_id),
        )
        return existing is not None

    async def set_bullet_refs(self, resume_id: int, bullet_ids: Sequence[int]) -> None:
        await self._session.execute(
            delete(ResumeBulletRef).where(ResumeBulletRef.resume_id == resume_id)
        )
        for bullet_id in bullet_ids:
            self._session.add(ResumeBulletRef(resume_id=resume_id, bullet_id=bullet_id))
        await self._session.flush()

    async def add_revision(self, revision: ResumeRevision) -> None:
        self._session.add(revision)
        await self._session.flush()

    async def ids_referencing_variant(self, user_id: int, variant_id: int) -> Sequence[int]:
        # A live resume projects an identity by referencing a variant id in its
        # document header. Finalized resumes inline a frozen snapshot instead (no
        # header variant id), so they never match; archived resumes are excluded
        # because a re-point only concerns living work. Scoped to the owner so a
        # variant archive never reaches another account's resume.
        result = await self._session.execute(
            select(Resume.id).where(
                Resume.user_id == user_id,
                Resume.archived_at.is_(None),
                Resume.document[("header", "identity_variant_id")].astext == str(variant_id),
            )
        )
        return list(result.scalars().all())

    async def used_in_count(self, bullet_id: int) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(ResumeBulletRef)
            .where(ResumeBulletRef.bullet_id == bullet_id)
        )
        return result.scalar_one()

    async def used_in_counts(self, bullet_ids: Sequence[int]) -> dict[int, int]:
        # The batched form of used_in_count: one grouped count for a whole page of
        # bullets, so a library list read never issues one query per bullet. Ids with
        # no reference row are simply absent from the grouped result.
        if not bullet_ids:
            return {}
        result = await self._session.execute(
            select(ResumeBulletRef.bullet_id, func.count())
            .where(ResumeBulletRef.bullet_id.in_(bullet_ids))
            .group_by(ResumeBulletRef.bullet_id)
        )
        # The grouped (bullet_id, count) rows map directly to the returned dict.
        return dict(result.tuples().all())
