"""Sources persistence: the repository interface and its SQLAlchemy binding.

The service depends on the :class:`SourceRepository` interface and receives a
resolved integer ``user_id``; tests substitute an in-memory repository at this
interface while production binds :class:`SqlAlchemySourceRepository` over a
request-scoped ``AsyncSession``. Every read is scoped to ``user_id`` so a source
another account owns is invisible (the service turns a miss into a 404, never a
cross-account leak).

Transaction ownership stays with the service: :meth:`add` flushes to mint the
base id and bind the subtype's composite FK, but the ``transaction`` boundary the
service wraps its write in is what commits. Mutating a row returned by
:meth:`get_detail` inside that same boundary persists via the unit of work.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from sqlalchemy import select

from floresu.core.db import fetch_optional
from floresu.profile.models import SUBTYPE_MODELS, Source, SourceKind, SourceSubtype

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


class SourceRepository(Protocol):
    """Data access for sources, scoped to what the service needs."""

    async def add(self, source: Source, subtype: SourceSubtype) -> None: ...

    async def get(self, user_id: int, source_id: int) -> Source | None: ...

    async def get_detail(
        self, user_id: int, source_id: int
    ) -> tuple[Source, SourceSubtype] | None: ...

    async def list(
        self, user_id: int, *, kind: SourceKind | None, include_archived: bool, limit: int
    ) -> Sequence[Source]: ...

    async def active_section(self, user_id: int, kind: SourceKind) -> Sequence[Source]: ...


class SqlAlchemySourceRepository:
    """The production repository over a request-scoped :class:`AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, source: Source, subtype: SourceSubtype) -> None:
        self._session.add(source)
        # Flush so the identity id is minted; the subtype's composite FK to
        # ``sources(id, kind)`` needs it before the subtype row is inserted.
        await self._session.flush()
        subtype.source_id = source.id
        self._session.add(subtype)
        await self._session.flush()

    async def get(self, user_id: int, source_id: int) -> Source | None:
        return await fetch_optional(
            self._session,
            select(Source).where(Source.id == source_id, Source.user_id == user_id),
        )

    async def get_detail(self, user_id: int, source_id: int) -> tuple[Source, SourceSubtype] | None:
        source = await self.get(user_id, source_id)
        if source is None:
            return None
        subtype_model = SUBTYPE_MODELS[source.kind]
        subtype = await fetch_optional(
            self._session,
            select(subtype_model).where(subtype_model.source_id == source_id),
        )
        if subtype is None:  # pragma: no cover - the composite FK guarantees a subtype row
            return None
        return source, cast("SourceSubtype", subtype)

    async def list(
        self, user_id: int, *, kind: SourceKind | None, include_archived: bool, limit: int
    ) -> Sequence[Source]:
        statement = select(Source).where(Source.user_id == user_id)
        if kind is not None:
            statement = statement.where(Source.kind == kind)
        if not include_archived:
            statement = statement.where(Source.archived_at.is_(None))
        statement = statement.order_by(Source.kind, Source.sort_order, Source.id).limit(limit)
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def active_section(self, user_id: int, kind: SourceKind) -> Sequence[Source]:
        # The full active section for one kind, ordered. Reorder needs every active
        # row (not a submitted subset) so it can enforce a complete-section submit;
        # unbounded on purpose (a section is small at P0 scale).
        statement = (
            select(Source)
            .where(
                Source.user_id == user_id,
                Source.kind == kind,
                Source.archived_at.is_(None),
            )
            .order_by(Source.sort_order, Source.id)
        )
        result = await self._session.execute(statement)
        return result.scalars().all()
