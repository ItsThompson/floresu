"""The narrow bullet-text resolver: resume references to canonical bullet text.

A resume ``library_ref`` item carries only a ``bullet_id``; the text lives on the
canonical bulletpoint. Resolving that text (to build a fully resolved revision
snapshot, and to validate that every referenced bullet is one the user owns) is
the one thing the resume domain needs from the library. This module defines the
narrow :class:`BulletTextResolver` port and its SQLAlchemy binding, so the service
depends on the small interface and tests substitute an in-memory resolver.

The query is user-scoped, so a resume can never resolve (and therefore never
reference in a snapshot) a bullet another account owns: an unowned or unknown id
is simply absent from the result, which the service surfaces as a validation
error. The dependency is one-directional (resumes reads ``library.models``); the
library never imports the resume domain, so there is no cycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlalchemy import select

from floresu.library.models import Bulletpoint

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


class BulletTextResolver(Protocol):
    """Resolve canonical bullet text for the ids a resume references, scoped to a user."""

    async def resolve(self, user_id: int, bullet_ids: Sequence[int]) -> dict[int, str]: ...


class SqlAlchemyBulletTextResolver:
    """The production resolver: reads ``bulletpoints.text`` over a request-scoped session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(self, user_id: int, bullet_ids: Sequence[int]) -> dict[int, str]:
        if not bullet_ids:
            return {}
        result = await self._session.execute(
            select(Bulletpoint.id, Bulletpoint.text).where(
                Bulletpoint.user_id == user_id, Bulletpoint.id.in_(bullet_ids)
            )
        )
        resolved: dict[int, str] = {}
        for bullet_id, bullet_text in result.all():
            resolved[bullet_id] = bullet_text
        return resolved
