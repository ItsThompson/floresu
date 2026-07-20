"""sources: the class-table-inheritance supertable

Adds the ground-truth sources layer: the ``source_kind`` enum, the ``sources``
base table (common columns, the ``kind`` discriminator, ``sort_order``,
``archived_at``, and the ``UNIQUE (id, kind)`` the subtypes bind to), and the four
kind-locked subtype tables (``roles`` / ``projects`` / ``certifications`` /
``education``). Each subtype pins its ``kind`` with a CHECK and binds
``(source_id, kind)`` to ``sources(id, kind)`` with a composite FK, so a subtype
row can never disagree with its base row. Every subtype FK cascades on the base
row's delete, and the base ``user_id`` FK cascades on account deletion.

Constraint, index, and enum names follow the deterministic convention so the ORM
models in ``floresu.profile.models`` autogenerate no diff and the downgrade is
reversible (drop the children, then the base table, then the enum).

Revision ID: 0006_sources
Revises: 0005_oauth
Create Date: 2026-07-20

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_sources"
down_revision: str | None = "0005_oauth"
branch_labels: str | None = None
depends_on: str | None = None

# ``create_type=False``: the type is created/dropped explicitly here so table
# create never re-emits ``CREATE TYPE``. One instance is reused by every column.
source_kind_enum = postgresql.ENUM(
    "role", "project", "certification", "education", name="source_kind", create_type=False
)


def _kind_locked_table(table: str, kind: str, *columns: sa.Column) -> None:
    """Create a subtype table: the shared key columns, its CHECK, and composite FK."""
    op.create_table(
        table,
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", source_kind_enum, nullable=False),
        *columns,
        sa.PrimaryKeyConstraint("source_id", name=f"pk_{table}"),
        # The ``ck`` naming convention (target metadata) wraps this to
        # ``ck_<table>_kind``; passing the full name would double the prefix.
        sa.CheckConstraint(f"kind = '{kind}'", name="kind"),
        sa.ForeignKeyConstraint(
            ["source_id", "kind"],
            ["sources.id", "sources.kind"],
            name=f"fk_{table}_source_id_sources",
            ondelete="CASCADE",
        ),
    )


def upgrade() -> None:
    source_kind_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "sources",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", source_kind_enum, nullable=False),
        sa.Column("display_label", sa.Text(), nullable=False),
        sa.Column("date_start", sa.Date(), nullable=True),
        sa.Column("date_end", sa.Date(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sources"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_sources_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("id", "kind", name="uq_sources_id_kind"),
    )
    op.create_index(
        "ix_sources_user_id_kind_sort_order",
        "sources",
        ["user_id", "kind", "sort_order"],
        unique=False,
    )

    _kind_locked_table(
        "roles",
        "role",
        sa.Column("company", sa.Text(), nullable=False),
        sa.Column("job_title", sa.Text(), nullable=False),
        sa.Column(
            "title_aliases",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("location", sa.Text(), nullable=True),
    )
    _kind_locked_table(
        "projects",
        "project",
        sa.Column(
            "links", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
    )
    _kind_locked_table(
        "certifications",
        "certification",
        sa.Column("issuer", sa.Text(), nullable=False),
        sa.Column("credential_id", sa.Text(), nullable=True),
    )
    _kind_locked_table(
        "education",
        "education",
        sa.Column("institution", sa.Text(), nullable=False),
        sa.Column("degree", sa.Text(), nullable=True),
        sa.Column("field", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("education")
    op.drop_table("certifications")
    op.drop_table("projects")
    op.drop_table("roles")
    op.drop_index("ix_sources_user_id_kind_sort_order", table_name="sources")
    op.drop_table("sources")
    source_kind_enum.drop(op.get_bind(), checkfirst=True)
