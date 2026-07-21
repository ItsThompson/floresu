"""Skills persistence: the repository interface and its SQLAlchemy binding.

The service depends on the :class:`SkillRepository` interface and receives a
resolved integer ``user_id``; tests substitute an in-memory repository at this
interface while production binds :class:`SqlAlchemySkillRepository` over a
request-scoped ``AsyncSession``. Every read is scoped to ``user_id`` so another
account's skill is invisible (the service turns a miss into a 404, never a
cross-account leak).

The usage count is a single cross-domain read: it joins the canonical worklog
``tags`` / ``worklog_tag`` tables (reused, never re-declared here) so a skill's
name is matched against the tag labels actually used on active worklog entries.

Transaction ownership stays with the service: :meth:`add` flushes to mint the id,
but the ``transaction`` boundary the service wraps its write in is what commits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlalchemy import func, select

from floresu.core.db import fetch_optional
from floresu.profile.skills.models import Skill
from floresu.worklog.models import Tag, WorklogEntry, WorklogTag

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


class SkillRepository(Protocol):
    """Data access for skills plus the cross-domain usage-count read."""

    async def add(self, skill: Skill) -> None: ...

    async def get(self, user_id: int, skill_id: int) -> Skill | None: ...

    async def list(
        self, user_id: int, *, include_archived: bool, limit: int
    ) -> Sequence[Skill]: ...

    async def active_section(self, user_id: int) -> Sequence[Skill]: ...

    async def usage_counts(self, user_id: int, names: Sequence[str]) -> dict[str, int]: ...


class SqlAlchemySkillRepository:
    """The production repository over a request-scoped :class:`AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, skill: Skill) -> None:
        self._session.add(skill)
        # Flush so the identity id is minted and the ``UNIQUE (user_id, name)``
        # breach (a duplicate curated name) surfaces here, where the service maps
        # it to a Conflict, rather than at commit.
        await self._session.flush()

    async def get(self, user_id: int, skill_id: int) -> Skill | None:
        return await fetch_optional(
            self._session,
            select(Skill).where(Skill.id == skill_id, Skill.user_id == user_id),
        )

    async def list(self, user_id: int, *, include_archived: bool, limit: int) -> Sequence[Skill]:
        statement = select(Skill).where(Skill.user_id == user_id)
        if not include_archived:
            statement = statement.where(Skill.archived_at.is_(None))
        statement = statement.order_by(Skill.sort_order, Skill.id).limit(limit)
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def active_section(self, user_id: int) -> Sequence[Skill]:
        # The user's full active skill list, ordered. Reorder needs every active
        # row (not a submitted subset) so it can enforce a complete-list submit;
        # unbounded on purpose (a curated list is small at P0 scale).
        statement = (
            select(Skill)
            .where(Skill.user_id == user_id, Skill.archived_at.is_(None))
            .order_by(Skill.sort_order, Skill.id)
        )
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def usage_counts(self, user_id: int, names: Sequence[str]) -> dict[str, int]:
        """Count active worklog entries tagged with each of ``names`` (one query).

        Usage is derived, not stored: a skill's name is matched exactly against the
        per-user tag labels used on non-archived worklog entries. Bullet-tag
        matches would be unioned in once bullets carry tags; no such table exists
        yet, so worklog is the whole corpus. A name with no matching tag maps to 0.
        """
        if not names:
            return {}
        statement = (
            select(Tag.label, func.count(WorklogTag.worklog_id))
            .join(WorklogTag, WorklogTag.tag_id == Tag.id)
            .join(WorklogEntry, WorklogEntry.id == WorklogTag.worklog_id)
            .where(
                Tag.user_id == user_id,
                Tag.label.in_(names),
                WorklogEntry.archived_at.is_(None),
            )
            .group_by(Tag.label)
        )
        result = await self._session.execute(statement)
        counts: dict[str, int] = {}
        for label, count in result.all():
            counts[label] = count
        return {name: counts.get(name, 0) for name in names}
