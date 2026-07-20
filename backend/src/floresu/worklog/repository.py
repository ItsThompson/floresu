"""Worklog persistence: the repository interface and its SQLAlchemy binding.

The service depends on the :class:`WorklogRepository` interface and receives a
resolved integer ``user_id``; tests substitute an in-memory repository at this
interface while production binds :class:`SqlAlchemyWorklogRepository` over a
request-scoped ``AsyncSession``. Every entry and tag read is scoped to ``user_id``
so another account's row is invisible (the service turns a miss into a 404, never
a cross-account leak), and attachment ownership is checked through
:meth:`owned_source_ids` so an entry can never attach a source it does not own.

Transaction ownership stays with the service: :meth:`add` and
:meth:`get_or_create_tag` flush to mint ids, and the edge setters replace an
entry's edges, but the ``transaction`` boundary the service wraps its write in is
what commits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlalchemy import delete, select

from floresu.core.db import fetch_optional
from floresu.profile.models import Source
from floresu.worklog.models import Tag, WorklogEntry, WorklogSource, WorklogTag

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


class WorklogRepository(Protocol):
    """Data access for worklog entries, tags, and their attachment edges."""

    async def add(self, entry: WorklogEntry) -> None: ...

    async def get(self, user_id: int, worklog_id: int) -> WorklogEntry | None: ...

    async def list_entries(
        self, user_id: int, *, include_archived: bool, limit: int
    ) -> Sequence[WorklogEntry]: ...

    async def owned_source_ids(self, user_id: int, source_ids: Sequence[int]) -> set[int]: ...

    async def get_or_create_tag(self, user_id: int, label: str) -> Tag: ...

    async def list_tags(self, user_id: int) -> Sequence[Tag]: ...

    async def set_sources(self, worklog_id: int, source_ids: Sequence[int]) -> None: ...

    async def set_tags(self, worklog_id: int, tag_ids: Sequence[int]) -> None: ...

    async def tag_labels_by_worklog(self, worklog_ids: Sequence[int]) -> dict[int, list[str]]: ...

    async def source_ids_by_worklog(self, worklog_ids: Sequence[int]) -> dict[int, list[int]]: ...

    async def bullet_ids_by_worklog(self, worklog_ids: Sequence[int]) -> dict[int, list[int]]: ...


class SqlAlchemyWorklogRepository:
    """The production repository over a request-scoped :class:`AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: WorklogEntry) -> None:
        self._session.add(entry)
        # Flush so the identity id is minted; the edge rows need it before insert.
        await self._session.flush()

    async def get(self, user_id: int, worklog_id: int) -> WorklogEntry | None:
        return await fetch_optional(
            self._session,
            select(WorklogEntry).where(
                WorklogEntry.id == worklog_id, WorklogEntry.user_id == user_id
            ),
        )

    async def list_entries(
        self, user_id: int, *, include_archived: bool, limit: int
    ) -> Sequence[WorklogEntry]:
        statement = select(WorklogEntry).where(WorklogEntry.user_id == user_id)
        if not include_archived:
            statement = statement.where(WorklogEntry.archived_at.is_(None))
        statement = statement.order_by(
            WorklogEntry.entry_date.desc(), WorklogEntry.id.desc()
        ).limit(limit)
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def owned_source_ids(self, user_id: int, source_ids: Sequence[int]) -> set[int]:
        if not source_ids:
            return set()
        result = await self._session.execute(
            select(Source.id).where(Source.user_id == user_id, Source.id.in_(source_ids))
        )
        return set(result.scalars().all())

    async def get_or_create_tag(self, user_id: int, label: str) -> Tag:
        existing = await fetch_optional(
            self._session,
            select(Tag).where(Tag.user_id == user_id, Tag.label == label),
        )
        if existing is not None:
            return existing
        tag = Tag(user_id=user_id, label=label)
        self._session.add(tag)
        await self._session.flush()
        return tag

    async def list_tags(self, user_id: int) -> Sequence[Tag]:
        result = await self._session.execute(
            select(Tag).where(Tag.user_id == user_id).order_by(Tag.label)
        )
        return result.scalars().all()

    async def set_sources(self, worklog_id: int, source_ids: Sequence[int]) -> None:
        await self._session.execute(
            delete(WorklogSource).where(WorklogSource.worklog_id == worklog_id)
        )
        for source_id in source_ids:
            self._session.add(WorklogSource(worklog_id=worklog_id, source_id=source_id))
        await self._session.flush()

    async def set_tags(self, worklog_id: int, tag_ids: Sequence[int]) -> None:
        await self._session.execute(delete(WorklogTag).where(WorklogTag.worklog_id == worklog_id))
        for tag_id in tag_ids:
            self._session.add(WorklogTag(worklog_id=worklog_id, tag_id=tag_id))
        await self._session.flush()

    async def tag_labels_by_worklog(self, worklog_ids: Sequence[int]) -> dict[int, list[str]]:
        if not worklog_ids:
            return {}
        result = await self._session.execute(
            select(WorklogTag.worklog_id, Tag.label)
            .join(Tag, Tag.id == WorklogTag.tag_id)
            .where(WorklogTag.worklog_id.in_(worklog_ids))
            .order_by(Tag.label)
        )
        labels: dict[int, list[str]] = {}
        for worklog_id, label in result.all():
            labels.setdefault(worklog_id, []).append(label)
        return labels

    async def source_ids_by_worklog(self, worklog_ids: Sequence[int]) -> dict[int, list[int]]:
        if not worklog_ids:
            return {}
        result = await self._session.execute(
            select(WorklogSource.worklog_id, WorklogSource.source_id)
            .where(WorklogSource.worklog_id.in_(worklog_ids))
            .order_by(WorklogSource.source_id)
        )
        sources: dict[int, list[int]] = {}
        for worklog_id, source_id in result.all():
            sources.setdefault(worklog_id, []).append(source_id)
        return sources

    async def bullet_ids_by_worklog(self, worklog_ids: Sequence[int]) -> dict[int, list[int]]:
        # The bulletpoints and their ``bullet_worklog`` edges do not exist yet, so
        # no entry has framing bullets. This resolves the real edges once the
        # Library table lands; until then every entry's list is empty.
        return {}
