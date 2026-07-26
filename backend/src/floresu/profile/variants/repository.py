"""Identity-variant persistence: the repository interface and its SQLAlchemy binding.

The service depends on the :class:`IdentityVariantRepository` interface and receives
a resolved integer ``user_id``; tests substitute an in-memory repository at this
interface while production binds :class:`SqlAlchemyIdentityVariantRepository` over a
request-scoped ``AsyncSession``. Every read is scoped to ``user_id`` so another
account's variant is invisible (the service turns a miss into a 404, never a
cross-account leak).

:meth:`current_default` resolves the user's single active default so the service can
flip it in the same transaction. Detecting and re-pointing the living resumes that
reference a variant is a resumes concept, so it is not here: the service reaches it
through the :class:`~floresu.profile.variants.repointing.ResumeVariantRepointer`
port (bound to the resume service at the composition root), which keeps this domain
free of any resumes import.

Transaction ownership stays with the service: :meth:`add` flushes to mint the id,
but the ``transaction`` boundary the service wraps its write in is what commits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlalchemy import select

from floresu.core.db import fetch_optional
from floresu.profile.variants.models import IdentityVariant

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


class IdentityVariantRepository(Protocol):
    """Data access for identity variants plus the living-resume reference seam."""

    async def add(self, variant: IdentityVariant) -> None: ...

    async def get(self, user_id: int, variant_id: int) -> IdentityVariant | None: ...

    async def list(
        self, user_id: int, *, include_archived: bool, limit: int
    ) -> Sequence[IdentityVariant]: ...

    async def current_default(self, user_id: int) -> IdentityVariant | None: ...


class SqlAlchemyIdentityVariantRepository:
    """The production repository over a request-scoped :class:`AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, variant: IdentityVariant) -> None:
        self._session.add(variant)
        # Flush so the identity id is minted and the ``UNIQUE (user_id, label)``
        # breach surfaces here, where the service maps it to a Conflict.
        await self._session.flush()

    async def get(self, user_id: int, variant_id: int) -> IdentityVariant | None:
        return await fetch_optional(
            self._session,
            select(IdentityVariant).where(
                IdentityVariant.id == variant_id, IdentityVariant.user_id == user_id
            ),
        )

    async def list(
        self, user_id: int, *, include_archived: bool, limit: int
    ) -> Sequence[IdentityVariant]:
        statement = select(IdentityVariant).where(IdentityVariant.user_id == user_id)
        if not include_archived:
            statement = statement.where(IdentityVariant.archived_at.is_(None))
        statement = statement.order_by(IdentityVariant.label, IdentityVariant.id).limit(limit)
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def current_default(self, user_id: int) -> IdentityVariant | None:
        # The single active default. The exactly-one-default invariant the service
        # maintains guarantees at most one active row matches.
        return await fetch_optional(
            self._session,
            select(IdentityVariant).where(
                IdentityVariant.user_id == user_id,
                IdentityVariant.is_default.is_(True),
                IdentityVariant.archived_at.is_(None),
            ),
        )
