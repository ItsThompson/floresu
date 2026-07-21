"""embeddings: pgvector storage plus the corpus full-text indexes

Ships the storage and lexical indexes hybrid search depends on (the retrieval and
fusion module itself lands in a later slice):

- The ``embed_item_kind`` enum (``worklog | bullet | source``) and the
  ``embeddings`` table: one ``vector(1536)`` per corpus item, keyed by the
  polymorphic ``(item_kind, item_id)`` primary key with **no** foreign key to the
  item (a new embeddable kind needs no schema change; a permanent delete removes
  the row explicitly). ``user_id`` cascades on account deletion. The dimension is
  pinned to the P0 provider here and in ``floresu.embedding.config``.
- An HNSW cosine ANN index (``vector_cosine_ops``) for approximate nearest
  neighbour, matching the normalized embedding outputs.
- GIN ``to_tsvector`` expression indexes over the corpus text columns for lexical
  full-text search: worklog title+description, source label+summary, role
  company+title, and bullet text. The ``'english'`` regconfig is passed explicitly
  so ``to_tsvector`` is immutable and therefore indexable.

The ``vector`` extension is enabled by the baseline migration (0001). Constraint
and index names follow the deterministic convention so the ``embeddings`` ORM
model in ``floresu.embedding.models`` autogenerates no diff and the downgrade is
reversible.

Revision ID: 0011_embeddings
Revises: 0010_resumes
Create Date: 2026-07-21

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0011_embeddings"
down_revision: str | None = "0010_resumes"
branch_labels: str | None = None
depends_on: str | None = None

# ``create_type=False``: the type is created/dropped explicitly here so table
# create never re-emits ``CREATE TYPE``. Mirrors the ``source_kind`` enum pattern.
embed_item_kind_enum = postgresql.ENUM(
    "worklog", "bullet", "source", name="embed_item_kind", create_type=False
)

# The corpus full-text GIN indexes, one per searchable text surface. Each is an
# expression index over ``to_tsvector('english', ...)`` with ``coalesce`` on the
# nullable columns so a null never voids the row's document.
_FTS_INDEXES: tuple[tuple[str, str, str], ...] = (
    (
        "ix_worklog_entries_fts",
        "worklog_entries",
        "to_tsvector('english'::regconfig, "
        "(title || ' '::text) || COALESCE(description, ''::text))",
    ),
    (
        "ix_bulletpoints_fts",
        "bulletpoints",
        "to_tsvector('english'::regconfig, text)",
    ),
    (
        "ix_sources_fts",
        "sources",
        "to_tsvector('english'::regconfig, "
        "(display_label || ' '::text) || COALESCE(summary, ''::text))",
    ),
    (
        "ix_roles_fts",
        "roles",
        "to_tsvector('english'::regconfig, (company || ' '::text) || job_title)",
    ),
)


def upgrade() -> None:
    embed_item_kind_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "embeddings",
        sa.Column("item_kind", embed_item_kind_enum, nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("vector", Vector(1536), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("item_kind", "item_id", name="pk_embeddings"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_embeddings_user_id_users", ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_embeddings_vector_hnsw",
        "embeddings",
        ["vector"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"vector": "vector_cosine_ops"},
    )
    for name, table, expression in _FTS_INDEXES:
        op.create_index(name, table, [sa.text(expression)], unique=False, postgresql_using="gin")


def downgrade() -> None:
    for name, table, _expression in _FTS_INDEXES:
        op.drop_index(name, table_name=table)
    op.drop_index("ix_embeddings_vector_hnsw", table_name="embeddings")
    op.drop_table("embeddings")
    embed_item_kind_enum.drop(op.get_bind(), checkfirst=True)
