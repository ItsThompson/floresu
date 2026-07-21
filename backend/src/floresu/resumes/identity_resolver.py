"""The narrow identity resolver: a resume header's variant to a frozen snapshot.

A living/draft resume header projects an identity by referencing an
``identity_variant_id``; rendering needs the concrete contact facts. This module
defines the narrow :class:`IdentityResolver` port and its SQLAlchemy binding, so the
render service depends on a small interface and tests substitute an in-memory
resolver. It reads ``profile.variants`` and produces a
:class:`~floresu.resumes.document.IdentitySnapshot`; the dependency is one-directional
(the profile domain never imports resumes), so there is no cycle.

Resolution is lenient so rendering never hard-fails on identity: a referenced
variant is resolved by id (regardless of archive state, since a resume that
references it should still render), falling back to the user's active default, and
finally to ``None`` (the header renders empty, and the template omits the blank
lines).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlalchemy import select

from floresu.core.db import fetch_optional
from floresu.profile.variants.models import IdentityVariant
from floresu.resumes.document import (
    IdentitySnapshot,
    IdentitySnapshotContact,
    IdentitySnapshotLink,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class IdentityResolver(Protocol):
    """Resolve the identity snapshot a resume header projects, scoped to a user."""

    async def resolve(self, user_id: int, variant_id: int | None) -> IdentitySnapshot | None: ...


class SqlAlchemyIdentityResolver:
    """The production resolver: reads ``identity_variants`` over a request-scoped session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(self, user_id: int, variant_id: int | None) -> IdentitySnapshot | None:
        variant: IdentityVariant | None = None
        if variant_id is not None:
            variant = await self._by_id(user_id, variant_id)
        if variant is None:
            variant = await self._default(user_id)
        if variant is None:
            return None
        return to_snapshot(variant)

    async def _by_id(self, user_id: int, variant_id: int) -> IdentityVariant | None:
        # By id and owner, regardless of archive state: a resume that references a
        # since-archived variant should still render with its identity.
        return await fetch_optional(
            self._session,
            select(IdentityVariant).where(
                IdentityVariant.id == variant_id, IdentityVariant.user_id == user_id
            ),
        )

    async def _default(self, user_id: int) -> IdentityVariant | None:
        return await fetch_optional(
            self._session,
            select(IdentityVariant).where(
                IdentityVariant.user_id == user_id,
                IdentityVariant.is_default.is_(True),
                IdentityVariant.archived_at.is_(None),
            ),
        )


def to_snapshot(variant: IdentityVariant) -> IdentitySnapshot:
    """Project an ``identity_variants`` row onto the frozen header snapshot shape."""
    return IdentitySnapshot(
        full_name=variant.full_name,
        contact=IdentitySnapshotContact.model_validate(variant.contact),
        links=[IdentitySnapshotLink.model_validate(link) for link in variant.links],
    )
