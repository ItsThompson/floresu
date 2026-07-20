"""accounts: onboarding flag + revoked-session blacklist

Extends the baseline ``users`` table with ``has_completed_onboarding`` (server
default false so existing rows read as un-onboarded) and adds the
``revoked_sessions`` blacklist that backs session refresh-rotation and logout:
each row revokes one session id (``sid``), and ``expires_at`` lets a later
cleanup job drop rows once the refresh token would have expired anyway.

Constraint and index names follow the deterministic convention
(``pk_revoked_sessions`` / ``ix_revoked_sessions_user_id``) so the ORM models in
``floresu.accounts.models`` autogenerate no diff and downgrades are reversible.

Revision ID: 0003_accounts_sessions
Revises: 0002_users
Create Date: 2026-07-20

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003_accounts_sessions"
down_revision: str | None = "0002_users"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "has_completed_onboarding",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_table(
        "revoked_sessions",
        sa.Column("sid", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("sid", name="pk_revoked_sessions"),
    )
    op.create_index("ix_revoked_sessions_user_id", "revoked_sessions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_revoked_sessions_user_id", table_name="revoked_sessions")
    op.drop_table("revoked_sessions")
    op.drop_column("users", "has_completed_onboarding")
