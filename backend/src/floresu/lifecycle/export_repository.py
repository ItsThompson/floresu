"""Read-only persistence for a data export: every record the account owns.

One repository, every read scoped to ``user_id``, so the export excludes other
users' data by construction (there is no query here that is not filtered by the
owner). It returns raw ORM rows and pre-grouped edge maps; the pure assembler in
:mod:`floresu.lifecycle.export` turns them into the serializable archive. Reads
are unbounded on purpose: an export is the whole record, and the P0 per-user
corpus is small.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlalchemy import select

from floresu.accounts.models import User
from floresu.core.db import fetch_optional
from floresu.library.models import Bulletpoint, BulletSource, BulletWorklog
from floresu.profile.models import Certification, Education, Project, Role, Source
from floresu.profile.skills.models import Skill
from floresu.profile.variants.models import IdentityVariant
from floresu.resumes.models import JobApplication, Resume
from floresu.worklog.models import Tag, WorklogEntry, WorklogSource, WorklogTag

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.profile.models import SourceSubtype


class ExportRepository(Protocol):
    """User-scoped reads across every domain the export archive spans."""

    async def account(self, user_id: int) -> User | None: ...
    async def worklog(self, user_id: int) -> Sequence[WorklogEntry]: ...
    async def worklog_tags(self, user_id: int) -> dict[int, list[str]]: ...
    async def worklog_sources(self, user_id: int) -> dict[int, list[int]]: ...
    async def sources(self, user_id: int) -> Sequence[Source]: ...
    async def source_details(self, user_id: int) -> dict[int, SourceSubtype]: ...
    async def bullets(self, user_id: int) -> Sequence[Bulletpoint]: ...
    async def bullet_sources(self, user_id: int) -> dict[int, list[int]]: ...
    async def bullet_worklogs(self, user_id: int) -> dict[int, list[int]]: ...
    async def skills(self, user_id: int) -> Sequence[Skill]: ...
    async def variants(self, user_id: int) -> Sequence[IdentityVariant]: ...
    async def tags(self, user_id: int) -> Sequence[Tag]: ...
    async def resumes(self, user_id: int) -> Sequence[Resume]: ...
    async def job_applications(self, user_id: int) -> Sequence[JobApplication]: ...


class SqlAlchemyExportRepository:
    """The production export reader over a request-scoped :class:`AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def account(self, user_id: int) -> User | None:
        return await fetch_optional(self._session, select(User).where(User.id == user_id))

    async def worklog(self, user_id: int) -> Sequence[WorklogEntry]:
        return (
            await self._session.scalars(
                select(WorklogEntry)
                .where(WorklogEntry.user_id == user_id)
                .order_by(WorklogEntry.id)
            )
        ).all()

    async def worklog_tags(self, user_id: int) -> dict[int, list[str]]:
        rows = await self._session.execute(
            select(WorklogTag.worklog_id, Tag.label)
            .join(Tag, Tag.id == WorklogTag.tag_id)
            .join(WorklogEntry, WorklogEntry.id == WorklogTag.worklog_id)
            .where(WorklogEntry.user_id == user_id)
        )
        return _group((row.worklog_id, row.label) for row in rows)

    async def worklog_sources(self, user_id: int) -> dict[int, list[int]]:
        rows = await self._session.execute(
            select(WorklogSource.worklog_id, WorklogSource.source_id)
            .join(WorklogEntry, WorklogEntry.id == WorklogSource.worklog_id)
            .where(WorklogEntry.user_id == user_id)
        )
        return _group((row.worklog_id, row.source_id) for row in rows)

    async def sources(self, user_id: int) -> Sequence[Source]:
        return (
            await self._session.scalars(
                select(Source).where(Source.user_id == user_id).order_by(Source.id)
            )
        ).all()

    async def source_details(self, user_id: int) -> dict[int, SourceSubtype]:
        """Map every source id to its typed subtype row (one query per kind)."""
        details: dict[int, SourceSubtype] = {}
        details.update(await self._subtype(Role, user_id))
        details.update(await self._subtype(Project, user_id))
        details.update(await self._subtype(Certification, user_id))
        details.update(await self._subtype(Education, user_id))
        return details

    async def _subtype[M: SourceSubtype](self, model: type[M], user_id: int) -> dict[int, M]:
        rows = await self._session.scalars(
            select(model)
            .join(Source, Source.id == model.source_id)
            .where(Source.user_id == user_id)
        )
        return {row.source_id: row for row in rows}

    async def bullets(self, user_id: int) -> Sequence[Bulletpoint]:
        return (
            await self._session.scalars(
                select(Bulletpoint).where(Bulletpoint.user_id == user_id).order_by(Bulletpoint.id)
            )
        ).all()

    async def bullet_sources(self, user_id: int) -> dict[int, list[int]]:
        rows = await self._session.execute(
            select(BulletSource.bullet_id, BulletSource.source_id)
            .join(Bulletpoint, Bulletpoint.id == BulletSource.bullet_id)
            .where(Bulletpoint.user_id == user_id)
        )
        return _group((row.bullet_id, row.source_id) for row in rows)

    async def bullet_worklogs(self, user_id: int) -> dict[int, list[int]]:
        rows = await self._session.execute(
            select(BulletWorklog.bullet_id, BulletWorklog.worklog_id)
            .join(Bulletpoint, Bulletpoint.id == BulletWorklog.bullet_id)
            .where(Bulletpoint.user_id == user_id)
        )
        return _group((row.bullet_id, row.worklog_id) for row in rows)

    async def skills(self, user_id: int) -> Sequence[Skill]:
        return (
            await self._session.scalars(
                select(Skill).where(Skill.user_id == user_id).order_by(Skill.sort_order, Skill.id)
            )
        ).all()

    async def variants(self, user_id: int) -> Sequence[IdentityVariant]:
        return (
            await self._session.scalars(
                select(IdentityVariant)
                .where(IdentityVariant.user_id == user_id)
                .order_by(IdentityVariant.id)
            )
        ).all()

    async def tags(self, user_id: int) -> Sequence[Tag]:
        return (
            await self._session.scalars(
                select(Tag).where(Tag.user_id == user_id).order_by(Tag.label)
            )
        ).all()

    async def resumes(self, user_id: int) -> Sequence[Resume]:
        return (
            await self._session.scalars(
                select(Resume).where(Resume.user_id == user_id).order_by(Resume.id)
            )
        ).all()

    async def job_applications(self, user_id: int) -> Sequence[JobApplication]:
        return (
            await self._session.scalars(
                select(JobApplication)
                .where(JobApplication.user_id == user_id)
                .order_by(JobApplication.id)
            )
        ).all()


def _group[K, V](pairs: Iterable[tuple[K, V]]) -> dict[K, list[V]]:
    """Group ``(key, value)`` pairs into ``{key: [values]}``, first-seen, de-duplicated."""
    grouped: dict[K, list[V]] = {}
    for key, value in pairs:
        bucket = grouped.setdefault(key, [])
        if value not in bucket:
            bucket.append(value)
    return grouped
