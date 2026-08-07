"""Resolve a corpus item's embeddable text, current hash, and archive state.

The pipeline reads an item by its ``(kind, id)`` to embed it. This resolver is the
one place that knows how each kind composes its searchable text and where its
freshness hash comes from:

- **worklog**: title + description; the stored ``content_hash`` gates re-embedding.
- **bullet**: the bullet text; the stored ``content_hash`` gates re-embedding.
- **source**: label + summary + (for a role) company + title. Sources carry no
  stored content hash yet, so the hash is derived from the composed text here;
  it is stable, so the idempotency gate still holds. Sources do not publish a
  re-embed trigger, so no source job flows today, but the read path is
  complete for when one does.

Reads are scoped to ``user_id`` (a defensive net at the trusted internal hop) and
go straight to the corpus tables via Core selects, mirroring how the search module
reads those tables. The resolver holds no state and performs no writes.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from sqlalchemy import select

from floresu.embedding.config import EmbedItemKind
from floresu.embedding.schemas import CorpusItem
from floresu.library.models import Bulletpoint
from floresu.profile.models import Role, Source
from floresu.worklog.models import WorklogEntry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class CorpusResolver:
    """Reads the embeddable content for a corpus item, scoped to its owner."""

    async def resolve(
        self, session: AsyncSession, user_id: int, kind: EmbedItemKind, item_id: int
    ) -> CorpusItem | None:
        """Return the item's text + current hash + archive state, or ``None`` if gone."""
        if kind is EmbedItemKind.WORKLOG:
            return await self._resolve_worklog(session, user_id, item_id)
        if kind is EmbedItemKind.BULLET:
            return await self._resolve_bullet(session, user_id, item_id)
        return await self._resolve_source(session, user_id, item_id)

    async def _resolve_worklog(
        self, session: AsyncSession, user_id: int, item_id: int
    ) -> CorpusItem | None:
        row = (
            await session.execute(
                select(
                    WorklogEntry.title,
                    WorklogEntry.description,
                    WorklogEntry.content_hash,
                    WorklogEntry.archived_at,
                ).where(WorklogEntry.id == item_id, WorklogEntry.user_id == user_id)
            )
        ).one_or_none()
        if row is None:
            return None
        text = _join(row.title, row.description)
        return CorpusItem(
            text=text, content_hash=row.content_hash, archived=row.archived_at is not None
        )

    async def _resolve_bullet(
        self, session: AsyncSession, user_id: int, item_id: int
    ) -> CorpusItem | None:
        row = (
            await session.execute(
                select(
                    Bulletpoint.text,
                    Bulletpoint.content_hash,
                    Bulletpoint.archived_at,
                ).where(Bulletpoint.id == item_id, Bulletpoint.user_id == user_id)
            )
        ).one_or_none()
        if row is None:
            return None
        return CorpusItem(
            text=row.text, content_hash=row.content_hash, archived=row.archived_at is not None
        )

    async def _resolve_source(
        self, session: AsyncSession, user_id: int, item_id: int
    ) -> CorpusItem | None:
        row = (
            await session.execute(
                select(
                    Source.display_label,
                    Source.summary,
                    Source.archived_at,
                    Role.company,
                    Role.job_title,
                )
                .select_from(Source)
                .outerjoin(Role, Role.source_id == Source.id)
                .where(Source.id == item_id, Source.user_id == user_id)
            )
        ).one_or_none()
        if row is None:
            return None
        role_line = f"{row.company} {row.job_title}" if row.company is not None else None
        text = _join(row.display_label, row.summary, role_line)
        return CorpusItem(text=text, content_hash=_hash(text), archived=row.archived_at is not None)


def _join(*parts: str | None) -> str:
    """Join the non-empty parts with blank lines into one embeddable document."""
    return "\n\n".join(part for part in parts if part)


def _hash(text: str) -> str:
    """Derive a stable content hash for a kind that stores none (sources)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
