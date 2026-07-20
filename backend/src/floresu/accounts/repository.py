"""Account persistence: the repository interface and its SQLAlchemy binding.

The service depends on the :class:`AccountRepository` interface and receives a
resolved identity, never building queries itself. Tests substitute an in-memory
repository at this interface; production binds :class:`SqlAlchemyAccountRepository`
over a request-scoped ``AsyncSession``.

Transaction ownership: ``core.db.get_session`` is yield-only (it does not commit),
so the transaction boundary lives here. The service calls :meth:`commit` after a
successful write and :meth:`rollback` on failure; this keeps the "one row or
None" reads and the commit policy in one place.

The resolved identity crosses the boundary as a string (the JWT ``sub`` / the
``X-User-ID`` wire form); this binding maps it to the bigint ``users.id``, so a
non-numeric id resolves to "no such user" rather than raising.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from floresu.accounts.models import RevokedSession, User
from floresu.core.db import fetch_optional

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.accounts.tokens import RefreshClaims


def _as_user_pk(user_id: str) -> int | None:
    """Map a resolved string identity to the bigint PK, or ``None`` if malformed."""
    try:
        return int(user_id)
    except ValueError:
        return None


class AccountRepository(Protocol):
    """Data access for accounts, scoped to the operations the service needs."""

    async def get_by_email(self, email: str) -> User | None: ...

    async def get_by_id(self, user_id: str) -> User | None: ...

    async def add_user(self, user: User) -> None: ...

    async def is_session_revoked(self, sid: str) -> bool: ...

    async def revoke_session(self, claims: RefreshClaims) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class SqlAlchemyAccountRepository:
    """The production repository over a request-scoped :class:`AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        return await fetch_optional(self._session, select(User).where(User.email == email))

    async def get_by_id(self, user_id: str) -> User | None:
        pk = _as_user_pk(user_id)
        if pk is None:
            return None
        return await fetch_optional(self._session, select(User).where(User.id == pk))

    async def add_user(self, user: User) -> None:
        self._session.add(user)
        # Flush so the identity column is assigned (``user.id`` populated) and a
        # unique-constraint breach surfaces as an IntegrityError now, inside the
        # service's try/except, rather than at commit time.
        await self._session.flush()

    async def is_session_revoked(self, sid: str) -> bool:
        found = await fetch_optional(
            self._session, select(RevokedSession.sid).where(RevokedSession.sid == sid)
        )
        return found is not None

    async def revoke_session(self, claims: RefreshClaims) -> None:
        # Insert-or-ignore: revoking an already-revoked session is idempotent
        # (logout twice, or a rotated session id re-submitted).
        statement = (
            pg_insert(RevokedSession)
            .values(sid=claims.sid, user_id=int(claims.user_id), expires_at=claims.expires_at)
            .on_conflict_do_nothing(index_elements=[RevokedSession.sid])
        )
        await self._session.execute(statement)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
