"""skills and identity_variants: the curated profile-family tables

Adds two per-user profile-family tables. ``skills`` is a curated list (``name``
unique per user, ``sort_order`` for the curated order, soft ``archived_at``); it
carries no timestamps, matching the data-model DDL for this lightweight row and its
``tags`` sibling. ``identity_variants`` is a labeled contact set (``label`` unique
per user, ``full_name``, ``contact`` and ``links`` JSONB, an ``is_default`` flag,
soft ``archived_at``, and ``created_at``/``updated_at``); the exactly-one-default
invariant is enforced in the service, so ``is_default`` is a plain boolean here.

Both tables cascade on account deletion. Constraint and index names follow the
deterministic convention so the ORM models in ``floresu.profile.skills.models`` and
``floresu.profile.variants.models`` autogenerate no diff and the downgrade is
reversible.

Revision ID: 0008_skills_identity_variants
Revises: 0007_worklog
Create Date: 2026-07-20

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_skills_identity_variants"
down_revision: str | None = "0007_worklog"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_skills"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_skills_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("user_id", "name", name="uq_skills_user_id"),
    )
    op.create_index(
        "ix_skills_user_id_sort_order", "skills", ["user_id", "sort_order"], unique=False
    )

    op.create_table(
        "identity_variants",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("contact", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("links", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_identity_variants"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_identity_variants_user_id_users",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", "label", name="uq_identity_variants_user_id"),
    )


def downgrade() -> None:
    op.drop_table("identity_variants")
    op.drop_index("ix_skills_user_id_sort_order", table_name="skills")
    op.drop_table("skills")
