"""worklog: entries, tags, and the source/tag attachment edges

Adds the worklog domain: the ``worklog_entries`` timeline table (title,
``entry_date``, description, the ``content_hash`` that gates re-embedding, and the
soft ``archived_at``), the per-user ``tags`` table (``UNIQUE (user_id, label)`` so
a label is reused not duplicated), and the two many-to-many edge tables
``worklog_source`` (entry attaches to sources) and ``worklog_tag`` (entry carries
tags). Every edge cascades on either endpoint's delete; the entry and tag rows
cascade on account deletion.

``worklog_source`` references ``sources(id)``, so this slice chains after 0006.
Constraint and index names follow the deterministic convention so the ORM models
in ``floresu.worklog.models`` autogenerate no diff and the downgrade is reversible.

Revision ID: 0007_worklog
Revises: 0006_sources
Create Date: 2026-07-20

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0007_worklog"
down_revision: str | None = "0006_sources"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "worklog_entries",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_worklog_entries"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_worklog_entries_user_id_users", ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_worklog_entries_user_id_entry_date",
        "worklog_entries",
        ["user_id", "entry_date"],
        unique=False,
    )

    op.create_table(
        "tags",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_tags"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_tags_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("user_id", "label", name="uq_tags_user_id"),
    )

    op.create_table(
        "worklog_source",
        sa.Column("worklog_id", sa.BigInteger(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("worklog_id", "source_id", name="pk_worklog_source"),
        sa.ForeignKeyConstraint(
            ["worklog_id"],
            ["worklog_entries.id"],
            name="fk_worklog_source_worklog_id_worklog_entries",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_worklog_source_source_id_sources",
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "worklog_tag",
        sa.Column("worklog_id", sa.BigInteger(), nullable=False),
        sa.Column("tag_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("worklog_id", "tag_id", name="pk_worklog_tag"),
        sa.ForeignKeyConstraint(
            ["worklog_id"],
            ["worklog_entries.id"],
            name="fk_worklog_tag_worklog_id_worklog_entries",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["tags.id"], name="fk_worklog_tag_tag_id_tags", ondelete="CASCADE"
        ),
    )


def downgrade() -> None:
    op.drop_table("worklog_tag")
    op.drop_table("worklog_source")
    op.drop_table("tags")
    op.drop_index("ix_worklog_entries_user_id_entry_date", table_name="worklog_entries")
    op.drop_table("worklog_entries")
