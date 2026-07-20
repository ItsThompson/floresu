"""oauth: authorization-server tables

Adds the five OAuth 2.1 AS tables: ``oauth_clients`` (DCR),
``oauth_auth_requests`` (parked authorize requests), ``oauth_authorization_codes``
(one-time PKCE-bound codes), ``oauth_refresh_tokens`` (rotating refresh, stored
hashed), and ``oauth_grants`` (the connected-client relationship, tracking a
connected time and a last-active time). Chained after the accounts slice to keep
a single linear head.

Constraint and index names follow the deterministic convention so the ORM models
in ``floresu.oauth.models`` autogenerate no structural diff and downgrades are
reversible.

Revision ID: 0004_oauth
Revises: 0003_accounts_sessions
Create Date: 2026-07-20

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_oauth"
down_revision: str | None = "0003_accounts_sessions"
branch_labels: str | None = None
depends_on: str | None = None


def _created_at() -> sa.Column[sa.DateTime]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "oauth_clients",
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("client_name", sa.String(length=200), nullable=False),
        sa.Column("redirect_uris", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("grant_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scope", sa.String(length=500), nullable=False),
        sa.Column("token_endpoint_auth_method", sa.String(length=32), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("client_id", name="pk_oauth_clients"),
    )

    op.create_table(
        "oauth_auth_requests",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("redirect_uri", sa.String(length=2000), nullable=False),
        sa.Column("scope", sa.String(length=500), nullable=False),
        sa.Column("state", sa.String(length=500), nullable=True),
        sa.Column("code_challenge", sa.String(length=128), nullable=False),
        sa.Column("code_challenge_method", sa.String(length=8), nullable=False),
        sa.Column("resource", sa.String(length=500), nullable=False),
        _created_at(),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_oauth_auth_requests"),
    )

    op.create_table(
        "oauth_authorization_codes",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("redirect_uri", sa.String(length=2000), nullable=False),
        sa.Column("scope", sa.String(length=500), nullable=False),
        sa.Column("code_challenge", sa.String(length=128), nullable=False),
        sa.Column("code_challenge_method", sa.String(length=8), nullable=False),
        sa.Column("resource", sa.String(length=500), nullable=False),
        sa.Column("used", sa.Boolean(), server_default=sa.false(), nullable=False),
        _created_at(),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_oauth_authorization_codes"),
    )
    op.create_index(
        "ix_oauth_authorization_codes_user_id",
        "oauth_authorization_codes",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "oauth_refresh_tokens",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("grant_id", sa.String(length=64), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=500), nullable=False),
        sa.Column("resource", sa.String(length=500), nullable=False),
        sa.Column("revoked", sa.Boolean(), server_default=sa.false(), nullable=False),
        _created_at(),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("token_hash", name="pk_oauth_refresh_tokens"),
    )
    op.create_index(
        "ix_oauth_refresh_tokens_grant_id", "oauth_refresh_tokens", ["grant_id"], unique=False
    )
    op.create_index(
        "ix_oauth_refresh_tokens_user_id", "oauth_refresh_tokens", ["user_id"], unique=False
    )

    op.create_table(
        "oauth_grants",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=500), nullable=False),
        sa.Column(
            "authorized_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_active_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_oauth_grants"),
        sa.UniqueConstraint("user_id", "client_id", name="uq_oauth_grants_user_id"),
    )
    op.create_index("ix_oauth_grants_user_id", "oauth_grants", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_oauth_grants_user_id", table_name="oauth_grants")
    op.drop_table("oauth_grants")
    op.drop_index("ix_oauth_refresh_tokens_user_id", table_name="oauth_refresh_tokens")
    op.drop_index("ix_oauth_refresh_tokens_grant_id", table_name="oauth_refresh_tokens")
    op.drop_table("oauth_refresh_tokens")
    op.drop_index("ix_oauth_authorization_codes_user_id", table_name="oauth_authorization_codes")
    op.drop_table("oauth_authorization_codes")
    op.drop_table("oauth_auth_requests")
    op.drop_table("oauth_clients")
