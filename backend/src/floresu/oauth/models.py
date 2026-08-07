"""OAuth 2.1 AS persistence models.

Five tables back the AS:

- ``oauth_clients``: Dynamic Client Registration records (RFC 7591); open
  registration at P0, public clients (PKCE, no secret).
- ``oauth_auth_requests``: authorize requests **parked** server-side under an
  opaque ``auth_request_id`` so the SPA only round-trips the id, not the OAuth
  params. Short-lived.
- ``oauth_authorization_codes``: one-time codes minted at consent, PKCE-bound.
- ``oauth_refresh_tokens``: rotating refresh tokens, stored only as a SHA-256
  hash; ``revoked`` supports rotation and replay rejection.
- ``oauth_grants``: the connected-client relationship (one per user+client) that
  ``/me/clients`` lists and revokes. ``authorized_at`` is the connected time and
  ``last_active_at`` the last token activity, so the list shows both.

There is no OAuth-specific audit table here: agent-grant provenance flows through
the shared write-event/audit seam, and issuance is observed via
structured logs plus the ``oauth_tokens_issued_total`` metric.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from floresu.core.orm import Base

# Opaque server-minted identifiers/secrets are url-safe tokens (~43 chars) or uuid
# hex (32); 64 leaves headroom. Token hashes are SHA-256 hex (64 chars exactly).
_ID_LEN = 64
_HASH_LEN = 64
# ``user_id`` is the resolved identity string (the session ``sub`` / X-User-ID
# wire form), which the accounts repository maps to the bigint ``users.id``.
_USER_ID_LEN = 32


class OAuthClient(Base):
    """A dynamically registered client. ``client_id`` is server-minted, opaque."""

    __tablename__ = "oauth_clients"

    client_id: Mapped[str] = mapped_column(String(_ID_LEN), primary_key=True)
    client_name: Mapped[str] = mapped_column(String(200))
    redirect_uris: Mapped[list[str]] = mapped_column(JSONB)
    grant_types: Mapped[list[str]] = mapped_column(JSONB)
    response_types: Mapped[list[str]] = mapped_column(JSONB)
    scope: Mapped[str] = mapped_column(String(500))
    token_endpoint_auth_method: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OAuthAuthRequest(Base):
    """A parked authorize request, addressed by an opaque ``auth_request_id``."""

    __tablename__ = "oauth_auth_requests"

    id: Mapped[str] = mapped_column(String(_ID_LEN), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(_ID_LEN))
    redirect_uri: Mapped[str] = mapped_column(String(2000))
    scope: Mapped[str] = mapped_column(String(500))
    state: Mapped[str | None] = mapped_column(String(500), nullable=True)
    code_challenge: Mapped[str] = mapped_column(String(128))
    code_challenge_method: Mapped[str] = mapped_column(String(8))
    resource: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OAuthAuthorizationCode(Base):
    """A one-time authorization code bound to a user, client, and PKCE challenge.

    The row is retained (``used`` flips true on first exchange) rather than deleted
    so a replay of an already-consumed code is distinguishable from an unknown
    code and can revoke the tokens it issued (OAuth 2.1 replay defense). Expired
    rows are reaped by the periodic sweep.
    """

    __tablename__ = "oauth_authorization_codes"

    code: Mapped[str] = mapped_column(String(_ID_LEN), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(_ID_LEN))
    user_id: Mapped[str] = mapped_column(String(_USER_ID_LEN), index=True)
    redirect_uri: Mapped[str] = mapped_column(String(2000))
    scope: Mapped[str] = mapped_column(String(500))
    code_challenge: Mapped[str] = mapped_column(String(128))
    code_challenge_method: Mapped[str] = mapped_column(String(8))
    resource: Mapped[str] = mapped_column(String(500))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OAuthRefreshToken(Base):
    """A rotating refresh token, stored only as a hash; ``revoked`` gates reuse."""

    __tablename__ = "oauth_refresh_tokens"

    token_hash: Mapped[str] = mapped_column(String(_HASH_LEN), primary_key=True)
    grant_id: Mapped[str] = mapped_column(String(_ID_LEN), index=True)
    client_id: Mapped[str] = mapped_column(String(_ID_LEN))
    user_id: Mapped[str] = mapped_column(String(_USER_ID_LEN), index=True)
    scope: Mapped[str] = mapped_column(String(500))
    resource: Mapped[str] = mapped_column(String(500))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OAuthGrant(Base):
    """The connected-client relationship: one active authorization per user+client.

    ``authorized_at`` is when consent established (or re-established) the current
    connection; ``last_active_at`` tracks the most recent token issuance/refresh,
    so ``/me/clients`` can show both a connected time and a last-active time.
    """

    __tablename__ = "oauth_grants"
    __table_args__ = (UniqueConstraint("user_id", "client_id"),)

    id: Mapped[str] = mapped_column(String(_ID_LEN), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(_USER_ID_LEN), index=True)
    client_id: Mapped[str] = mapped_column(String(_ID_LEN))
    scope: Mapped[str] = mapped_column(String(500))
    authorized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
