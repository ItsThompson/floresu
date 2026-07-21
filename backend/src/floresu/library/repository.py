"""Library persistence: the repository interface and its SQLAlchemy binding.

The service depends on the :class:`LibraryRepository` interface and receives a
resolved integer ``user_id``; tests substitute an in-memory repository at this
interface while production binds :class:`SqlAlchemyLibraryRepository` over a
request-scoped ``AsyncSession``. Every bullet read is scoped to ``user_id`` so
another account's row is invisible (the service turns a miss into a 404, never a
cross-account leak), and edge-target ownership is checked through
:meth:`owned_source_ids` / :meth:`owned_worklog_ids` so a bullet can never frame a
source or worklog entry the user does not own.

Transaction ownership stays with the service: :meth:`add` flushes to mint the
bullet id the edge rows need, and the edge setters replace a bullet's edges, but
the ``transaction`` boundary the service wraps its write in is what commits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlalchemy import delete, select

from floresu.core.db import fetch_optional
from floresu.library.models import Bulletpoint, BulletSource, BulletWorklog
from floresu.profile.models import Source
from floresu.worklog.models import WorklogEntry

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


class LibraryRepository(Protocol):
    """Data access for bulletpoints and their two provenance-edge tables."""

    async def add(self, bullet: Bulletpoint) -> None: ...

    async def get(self, user_id: int, bullet_id: int) -> Bulletpoint | None: ...

    async def list_bullets(
        self, user_id: int, *, include_archived: bool, limit: int
    ) -> Sequence[Bulletpoint]: ...

    async def owned_source_ids(self, user_id: int, source_ids: Sequence[int]) -> set[int]: ...

    async def owned_worklog_ids(self, user_id: int, worklog_ids: Sequence[int]) -> set[int]: ...

    async def set_sources(self, bullet_id: int, source_ids: Sequence[int]) -> None: ...

    async def set_worklogs(self, bullet_id: int, worklog_ids: Sequence[int]) -> None: ...

    async def source_ids_by_bullet(self, bullet_ids: Sequence[int]) -> dict[int, list[int]]: ...

    async def worklog_ids_by_bullet(self, bullet_ids: Sequence[int]) -> dict[int, list[int]]: ...


class SqlAlchemyLibraryRepository:
    """The production repository over a request-scoped :class:`AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, bullet: Bulletpoint) -> None:
        self._session.add(bullet)
        # Flush so the identity id is minted; the edge rows need it before insert.
        await self._session.flush()

    async def get(self, user_id: int, bullet_id: int) -> Bulletpoint | None:
        return await fetch_optional(
            self._session,
            select(Bulletpoint).where(Bulletpoint.id == bullet_id, Bulletpoint.user_id == user_id),
        )

    async def list_bullets(
        self, user_id: int, *, include_archived: bool, limit: int
    ) -> Sequence[Bulletpoint]:
        statement = select(Bulletpoint).where(Bulletpoint.user_id == user_id)
        if not include_archived:
            statement = statement.where(Bulletpoint.archived_at.is_(None))
        statement = statement.order_by(Bulletpoint.id.desc()).limit(limit)
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def owned_source_ids(self, user_id: int, source_ids: Sequence[int]) -> set[int]:
        if not source_ids:
            return set()
        result = await self._session.execute(
            select(Source.id).where(Source.user_id == user_id, Source.id.in_(source_ids))
        )
        return set(result.scalars().all())

    async def owned_worklog_ids(self, user_id: int, worklog_ids: Sequence[int]) -> set[int]:
        if not worklog_ids:
            return set()
        result = await self._session.execute(
            select(WorklogEntry.id).where(
                WorklogEntry.user_id == user_id, WorklogEntry.id.in_(worklog_ids)
            )
        )
        return set(result.scalars().all())

    async def set_sources(self, bullet_id: int, source_ids: Sequence[int]) -> None:
        await self._session.execute(delete(BulletSource).where(BulletSource.bullet_id == bullet_id))
        for source_id in source_ids:
            self._session.add(BulletSource(bullet_id=bullet_id, source_id=source_id))
        await self._session.flush()

    async def set_worklogs(self, bullet_id: int, worklog_ids: Sequence[int]) -> None:
        await self._session.execute(
            delete(BulletWorklog).where(BulletWorklog.bullet_id == bullet_id)
        )
        for worklog_id in worklog_ids:
            self._session.add(BulletWorklog(bullet_id=bullet_id, worklog_id=worklog_id))
        await self._session.flush()

    async def source_ids_by_bullet(self, bullet_ids: Sequence[int]) -> dict[int, list[int]]:
        if not bullet_ids:
            return {}
        result = await self._session.execute(
            select(BulletSource.bullet_id, BulletSource.source_id)
            .where(BulletSource.bullet_id.in_(bullet_ids))
            .order_by(BulletSource.source_id)
        )
        sources: dict[int, list[int]] = {}
        for bullet_id, source_id in result.all():
            sources.setdefault(bullet_id, []).append(source_id)
        return sources

    async def worklog_ids_by_bullet(self, bullet_ids: Sequence[int]) -> dict[int, list[int]]:
        if not bullet_ids:
            return {}
        result = await self._session.execute(
            select(BulletWorklog.bullet_id, BulletWorklog.worklog_id)
            .where(BulletWorklog.bullet_id.in_(bullet_ids))
            .order_by(BulletWorklog.worklog_id)
        )
        worklogs: dict[int, list[int]] = {}
        for bullet_id, worklog_id in result.all():
            worklogs.setdefault(bullet_id, []).append(worklog_id)
        return worklogs
