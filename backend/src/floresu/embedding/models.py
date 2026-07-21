"""The ``embeddings`` ORM model: one vector per searchable corpus item.

Vectors live in this dedicated table keyed by a polymorphic ``(item_kind, item_id)``
reference with **no** foreign key to the item, so a new embeddable kind needs no
schema change and a permanent delete must explicitly remove the matching row
(there is nothing to cascade from the item side). The ``user_id`` foreign key is
the one cascade: deleting an account removes its vectors.

``content_hash`` mirrors the source row's hash at the moment the vector was
produced; the embedding pipeline compares it to gate re-embedding (a job whose
hash no longer matches the item is superseded and dropped; a row that already
carries the current hash is a no-op). ``model`` records which provider produced
the vector. The dimension is pinned to the P0 provider both here and in the
migration (see :data:`floresu.embedding.config.EMBEDDING_DIMENSION`).

This model is the single schema ``alembic/env.py`` imports so ``--autogenerate``
diffs the real table; it mirrors migration ``0010`` (the table, the HNSW cosine
ANN index, and the corpus full-text GIN indexes added to the sibling tables).
"""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from floresu.core.orm import Base
from floresu.embedding.config import EMBEDDING_DIMENSION, EmbedItemKind

# The native ``embed_item_kind`` enum, created by migration 0010 (``create_type``
# is False so table create/autogenerate never re-emits ``CREATE TYPE``).
# ``values_callable`` pins the stored labels to the enum values, matching the wire
# form, mirroring the ``source_kind`` enum in the profile domain.
EMBED_ITEM_KIND_ENUM = postgresql.ENUM(
    EmbedItemKind,
    name="embed_item_kind",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    create_type=False,
)


class Embedding(Base):
    """One semantic vector for a corpus item, keyed polymorphically with no item FK."""

    __tablename__ = "embeddings"

    item_kind: Mapped[EmbedItemKind] = mapped_column(EMBED_ITEM_KIND_ENUM, primary_key=True)
    item_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # The source item's content hash at embed time; gates re-embedding.
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    vector: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSION), nullable=False)
    # Provenance of which provider produced the vector.
    model: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # HNSW cosine ANN index: good recall/latency at per-user corpus sizes with
        # no training step. Cosine matches the normalized embedding outputs.
        Index(
            "ix_embeddings_vector_hnsw",
            "vector",
            postgresql_using="hnsw",
            postgresql_ops={"vector": "vector_cosine_ops"},
        ),
    )
