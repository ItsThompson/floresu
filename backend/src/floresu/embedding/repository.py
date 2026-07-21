"""Data access for the ``embeddings`` table: get, upsert, delete.

The service depends on the :class:`EmbeddingRepository` interface and receives a
concrete implementation, so tests bind an in-memory double at the only true
external boundary (Postgres) while production binds
:class:`SqlAlchemyEmbeddingRepository` over a real session.

The upsert is a single ``INSERT ... ON CONFLICT (item_kind, item_id) DO UPDATE`` so
a re-embed overwrites the vector, hash, and model in one statement and the
polymorphic primary key is the conflict target. Reads and deletes are keyed by the
same ``(item_kind, item_id)``; ``user_id`` is carried on write for the
account-deletion cascade. The repository holds the caller's session so it enlists
in the write's transaction; it owns no transaction boundary of its own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from floresu.embedding.models import Embedding

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.embedding.config import EmbedItemKind


class EmbeddingRepository(Protocol):
    """The data-access interface the embedding service depends on."""

    async def get(self, kind: EmbedItemKind, item_id: int) -> Embedding | None:
        """Load the stored embedding for an item, or ``None`` if it has none yet."""
        ...

    async def upsert(
        self,
        *,
        user_id: int,
        kind: EmbedItemKind,
        item_id: int,
        content_hash: str,
        vector: list[float],
        model: str,
    ) -> None:
        """Insert the vector, or overwrite the existing one for this item."""
        ...

    async def delete(self, kind: EmbedItemKind, item_id: int) -> None:
        """Remove an item's vector; a no-op if it has none (idempotent)."""
        ...


class SqlAlchemyEmbeddingRepository:
    """The Postgres-backed :class:`EmbeddingRepository`, bound over a session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, kind: EmbedItemKind, item_id: int) -> Embedding | None:
        return (
            await self._session.execute(
                select(Embedding).where(Embedding.item_kind == kind, Embedding.item_id == item_id)
            )
        ).scalar_one_or_none()

    async def upsert(
        self,
        *,
        user_id: int,
        kind: EmbedItemKind,
        item_id: int,
        content_hash: str,
        vector: list[float],
        model: str,
    ) -> None:
        statement = pg_insert(Embedding).values(
            item_kind=kind,
            item_id=item_id,
            user_id=user_id,
            content_hash=content_hash,
            vector=vector,
            model=model,
        )
        statement = statement.on_conflict_do_update(
            constraint="pk_embeddings",
            set_={
                "user_id": statement.excluded.user_id,
                "content_hash": statement.excluded.content_hash,
                "vector": statement.excluded.vector,
                "model": statement.excluded.model,
            },
        )
        await self._session.execute(statement)

    async def delete(self, kind: EmbedItemKind, item_id: int) -> None:
        await self._session.execute(
            sql_delete(Embedding).where(Embedding.item_kind == kind, Embedding.item_id == item_id)
        )
