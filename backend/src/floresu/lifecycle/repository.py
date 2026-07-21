"""Destructive persistence for the web-only lifecycle: hard deletes and cascade.

These are the only hard row deletes in the system. Every domain elsewhere keeps
archive soft; permanent delete lives here, behind the external app, and is issued
as user-scoped ``DELETE`` statements so the database's ``ON DELETE CASCADE`` FKs
remove the dependent subtype, edge, and revision rows (see the data model). The
polymorphic ``embeddings`` row has no FK to its item, so it is purged separately
by the service through the embedding repository, in the same transaction.

Each per-entity delete first reads the row's label (scoped to the owner) for the
audit summary and to detect a miss as a 404, then deletes it. Account deletion
removes the ``users`` row (cascading every ``user_id``-owned table, ``embeddings``
included) and separately clears the OAuth grant chain and session blacklist, which
carry the user id as an unconstrained string/int and so do not cascade.

Transaction ownership stays with the service: these methods only issue statements
against the shared session and the service's ``transaction`` boundary commits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlalchemy import delete, func, select

from floresu.accounts.models import RevokedSession, User
from floresu.core.db import fetch_optional
from floresu.library.models import Bulletpoint
from floresu.oauth.models import OAuthAuthorizationCode, OAuthGrant, OAuthRefreshToken
from floresu.profile.models import Source, SourceKind
from floresu.resumes.models import Resume
from floresu.worklog.models import WorklogEntry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Bulk deletes touch no ORM-loaded rows in this request-scoped session, so skip the
# identity-map synchronization pass SQLAlchemy would otherwise run.
_NO_SYNC = {"synchronize_session": False}


class LifecycleRepository(Protocol):
    """User-scoped hard deletes plus the account-deletion cascade helpers."""

    async def delete_worklog(self, user_id: int, worklog_id: int) -> str | None: ...

    async def delete_source(self, user_id: int, source_id: int) -> tuple[str, str] | None: ...

    async def delete_bullet(self, user_id: int, bullet_id: int) -> str | None: ...

    async def delete_resume(self, user_id: int, resume_id: int) -> str | None: ...

    async def count_active_agents(self, user_id_str: str) -> int: ...

    async def revoke_agents(self, user_id_str: str) -> None: ...

    async def clear_session_blacklist(self, user_id: int) -> None: ...

    async def delete_user(self, user_id: int) -> bool: ...


class SqlAlchemyLifecycleRepository:
    """The production repository over a request-scoped :class:`AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def delete_worklog(self, user_id: int, worklog_id: int) -> str | None:
        title = await fetch_optional(
            self._session,
            select(WorklogEntry.title).where(
                WorklogEntry.id == worklog_id, WorklogEntry.user_id == user_id
            ),
        )
        if title is None:
            return None
        await self._session.execute(
            delete(WorklogEntry)
            .where(WorklogEntry.id == worklog_id, WorklogEntry.user_id == user_id)
            .execution_options(**_NO_SYNC)
        )
        return title

    async def delete_source(self, user_id: int, source_id: int) -> tuple[str, str] | None:
        row = (
            await self._session.execute(
                select(Source.kind, Source.display_label).where(
                    Source.id == source_id, Source.user_id == user_id
                )
            )
        ).one_or_none()
        if row is None:
            return None
        kind: SourceKind = row.kind
        await self._session.execute(
            delete(Source)
            .where(Source.id == source_id, Source.user_id == user_id)
            .execution_options(**_NO_SYNC)
        )
        return kind.value, row.display_label

    async def delete_bullet(self, user_id: int, bullet_id: int) -> str | None:
        text = await fetch_optional(
            self._session,
            select(Bulletpoint.text).where(
                Bulletpoint.id == bullet_id, Bulletpoint.user_id == user_id
            ),
        )
        if text is None:
            return None
        await self._session.execute(
            delete(Bulletpoint)
            .where(Bulletpoint.id == bullet_id, Bulletpoint.user_id == user_id)
            .execution_options(**_NO_SYNC)
        )
        return text

    async def delete_resume(self, user_id: int, resume_id: int) -> str | None:
        title = await fetch_optional(
            self._session,
            select(Resume.title).where(Resume.id == resume_id, Resume.user_id == user_id),
        )
        if title is None:
            return None
        await self._session.execute(
            delete(Resume)
            .where(Resume.id == resume_id, Resume.user_id == user_id)
            .execution_options(**_NO_SYNC)
        )
        return title

    async def count_active_agents(self, user_id_str: str) -> int:
        count = await self._session.scalar(
            select(func.count())
            .select_from(OAuthGrant)
            .where(OAuthGrant.user_id == user_id_str, OAuthGrant.revoked_at.is_(None))
        )
        return int(count or 0)

    async def revoke_agents(self, user_id_str: str) -> None:
        """Remove every OAuth grant, refresh token, and code for the user.

        The OAuth tables carry the user id as an unconstrained string (no FK to
        ``users``), so they do not cascade on account deletion; deleting the grant
        chain here is what disconnects every connected agent (no refresh token
        survives to mint a new access token).
        """
        for model in (OAuthRefreshToken, OAuthAuthorizationCode, OAuthGrant):
            await self._session.execute(
                delete(model).where(model.user_id == user_id_str).execution_options(**_NO_SYNC)
            )

    async def clear_session_blacklist(self, user_id: int) -> None:
        await self._session.execute(
            delete(RevokedSession)
            .where(RevokedSession.user_id == user_id)
            .execution_options(**_NO_SYNC)
        )

    async def delete_user(self, user_id: int) -> bool:
        """Delete the ``users`` row; every ``user_id``-owned table cascades with it."""
        deleted = await self._session.scalar(
            delete(User).where(User.id == user_id).returning(User.id).execution_options(**_NO_SYNC)
        )
        return deleted is not None
