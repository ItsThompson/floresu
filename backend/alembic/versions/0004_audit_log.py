"""audit_log: append-only provenance backbone

Adds the ``audit_log`` table that records one row per content write and backs both
the activity feed and per-item history. ``id`` is a server-minted monotonic bigint
identity (it doubles as the SSE event id and the feed's ordering key). ``actor_type``
is the native ``actor_type`` enum ('human' | 'agent'); ``actor_label`` names the
agent and is null for a human. No field-level diff is stored (action + summary +
light JSONB metadata only), and rows cascade on account deletion via the
``user_id`` foreign key.

Constraint, index, and enum names follow the deterministic convention
(``pk_audit_log`` / ``fk_audit_log_user_id_users`` / ``ix_audit_log_user_id_id``)
so the ORM model in ``floresu.audit.models`` autogenerates no diff and the
downgrade is reversible. The composite ``(user_id, id)`` index serves the per-user,
newest-first reads (Postgres scans it backward for ``ORDER BY id DESC``).

Revision ID: 0004_audit_log
Revises: 0003_accounts_sessions
Create Date: 2026-07-20

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_audit_log"
down_revision: str | None = "0003_accounts_sessions"
branch_labels: str | None = None
depends_on: str | None = None

# ``create_type=False``: the type is created/dropped explicitly here so table
# create and ``--autogenerate`` never re-emit ``CREATE TYPE``.
actor_type_enum = postgresql.ENUM("human", "agent", name="actor_type", create_type=False)


def upgrade() -> None:
    actor_type_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_type", actor_type_enum, nullable=False),
        sa.Column("actor_label", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_audit_log_user_id_users",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_audit_log_user_id_id", "audit_log", ["user_id", "id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_log_user_id_id", table_name="audit_log")
    op.drop_table("audit_log")
    actor_type_enum.drop(op.get_bind(), checkfirst=True)
