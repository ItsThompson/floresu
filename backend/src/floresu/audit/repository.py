"""Audit-log persistence: the repository interface and its SQLAlchemy binding.

The service depends on the :class:`AuditRepository` interface; tests substitute an
in-memory repository and production binds :class:`SqlAlchemyAuditRepository` over a
request-scoped ``AsyncSession``. The write path (``add``) shares the content
write's session so the row commits or rolls back atomically with it; the read
paths back the activity feed and per-item history, both newest-first via the
monotonic ``id``.

Transaction ownership stays with the caller: ``add`` flushes (to mint the
monotonic ``id`` and surface any constraint breach now) but never commits. The
domain service's ``transaction`` boundary commits the content write and this row
together.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlalchemy import select

from floresu.audit.models import AuditLog

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


class AuditRepository(Protocol):
    """Data access for the audit log, scoped to what the service needs."""

    async def add(self, entry: AuditLog) -> None: ...

    async def activity_feed(self, user_id: int, *, limit: int) -> Sequence[AuditLog]: ...

    async def item_history(
        self, user_id: int, entity_type: str, entity_id: int, *, limit: int
    ) -> Sequence[AuditLog]: ...


class SqlAlchemyAuditRepository:
    """The production repository over a request-scoped :class:`AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: AuditLog) -> None:
        self._session.add(entry)
        # Flush so the monotonic identity id is assigned now (SSE needs it) and any
        # constraint breach surfaces inside the caller's transaction, not at commit.
        await self._session.flush()

    async def activity_feed(self, user_id: int, *, limit: int) -> Sequence[AuditLog]:
        statement = (
            select(AuditLog)
            .where(AuditLog.user_id == user_id)
            .order_by(AuditLog.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def item_history(
        self, user_id: int, entity_type: str, entity_id: int, *, limit: int
    ) -> Sequence[AuditLog]:
        statement = (
            select(AuditLog)
            .where(
                AuditLog.user_id == user_id,
                AuditLog.entity_type == entity_type,
                AuditLog.entity_id == entity_id,
            )
            .order_by(AuditLog.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return result.scalars().all()
