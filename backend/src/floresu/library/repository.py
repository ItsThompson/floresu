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

from typing import TYPE_CHECKING, Any, Protocol, cast

from sqlalchemy import delete, select, update

from floresu.core.db import fetch_optional, group_pairs_into_dict, owned_ids
from floresu.library.models import Bulletpoint, BulletSource, BulletWorklog
from floresu.profile.models import Source
from floresu.worklog.models import WorklogEntry

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession


class LibraryRepository(Protocol):
    """Data access for bulletpoints and their two provenance-edge tables."""

    async def add(self, bullet: Bulletpoint) -> None: ...

    async def get(self, user_id: int, bullet_id: int) -> Bulletpoint | None: ...

    async def list_bullets(
        self, user_id: int, *, include_archived: bool, limit: int
    ) -> Sequence[Bulletpoint]: ...

    async def update_text_if_revision(
        self, user_id: int, bullet_id: int, if_match: int, text: str, content_hash: str
    ) -> bool: ...

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

    async def update_text_if_revision(
        self, user_id: int, bullet_id: int, if_match: int, text: str, content_hash: str
    ) -> bool:
        # Compare-and-swap: advance the revision and rewrite text/hash in one atomic
        # statement, but only while the loaded revision still matches. The database
        # decides a same-revision race: exactly one concurrent writer matches
        # ``revision == if_match`` and increments, the loser matches 0 rows. The
        # rowcount, not a prior read, is the guard, so there is no lost update.
        result = await self._session.execute(
            update(Bulletpoint)
            .where(
                Bulletpoint.id == bullet_id,
                Bulletpoint.user_id == user_id,
                Bulletpoint.revision == if_match,
            )
            .values(revision=Bulletpoint.revision + 1, text=text, content_hash=content_hash)
        )
        # A DML execute yields a CursorResult; rowcount is the CAS's authoritative
        # hit count (1 on a match, 0 on a stale/raced token).
        return cast("CursorResult[Any]", result).rowcount == 1

    async def owned_source_ids(self, user_id: int, source_ids: Sequence[int]) -> set[int]:
        return await owned_ids(
            self._session,
            user_pk_column=Source.user_id,
            id_column=Source.id,
            user_pk=user_id,
            candidate_ids=source_ids,
        )

    async def owned_worklog_ids(self, user_id: int, worklog_ids: Sequence[int]) -> set[int]:
        return await owned_ids(
            self._session,
            user_pk_column=WorklogEntry.user_id,
            id_column=WorklogEntry.id,
            user_pk=user_id,
            candidate_ids=worklog_ids,
        )

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
        return group_pairs_into_dict(result.tuples().all())

    async def worklog_ids_by_bullet(self, bullet_ids: Sequence[int]) -> dict[int, list[int]]:
        if not bullet_ids:
            return {}
        result = await self._session.execute(
            select(BulletWorklog.bullet_id, BulletWorklog.worklog_id)
            .where(BulletWorklog.bullet_id.in_(bullet_ids))
            .order_by(BulletWorklog.worklog_id)
        )
        return group_pairs_into_dict(result.tuples().all())
