"""library: canonical bulletpoints and the two provenance-DAG edges

Adds the Library layer: the ``bulletpoints`` table (canonical reusable framings
with the ``content_hash`` that gates re-embedding, the optimistic ``revision``
token, and the soft ``archived_at``) and the two many-to-many edge tables
``bullet_source`` (bullet frames a source) and ``bullet_worklog`` (bullet frames a
worklog entry). With ``worklog_source`` from 0007 these are the three joins of the
provenance DAG. Every edge cascades on either endpoint's delete; the bullet row
cascades on account deletion.

``bullet_source`` references ``sources(id)`` and ``bullet_worklog`` references
``worklog_entries(id)``, so this slice chains after 0007. Constraint and index
names follow the deterministic convention so the ORM models in
``floresu.library.models`` autogenerate no diff and the downgrade is reversible.

Revision ID: 0008_library
Revises: 0007_worklog
Create Date: 2026-07-20

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0008_library"
down_revision: str | None = "0007_worklog"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "bulletpoints",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_bulletpoints"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_bulletpoints_user_id_users", ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_bulletpoints_user_id_id",
        "bulletpoints",
        ["user_id", "id"],
        unique=False,
    )

    op.create_table(
        "bullet_source",
        sa.Column("bullet_id", sa.BigInteger(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("bullet_id", "source_id", name="pk_bullet_source"),
        sa.ForeignKeyConstraint(
            ["bullet_id"],
            ["bulletpoints.id"],
            name="fk_bullet_source_bullet_id_bulletpoints",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_bullet_source_source_id_sources",
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "bullet_worklog",
        sa.Column("bullet_id", sa.BigInteger(), nullable=False),
        sa.Column("worklog_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("bullet_id", "worklog_id", name="pk_bullet_worklog"),
        sa.ForeignKeyConstraint(
            ["bullet_id"],
            ["bulletpoints.id"],
            name="fk_bullet_worklog_bullet_id_bulletpoints",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["worklog_id"],
            ["worklog_entries.id"],
            name="fk_bullet_worklog_worklog_id_worklog_entries",
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("bullet_worklog")
    op.drop_table("bullet_source")
    op.drop_index("ix_bulletpoints_user_id_id", table_name="bulletpoints")
    op.drop_table("bulletpoints")
