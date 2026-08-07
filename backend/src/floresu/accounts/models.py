"""Accounts ORM models: the ``users`` table and the revoked-session blacklist.

``email`` is stored normalized (lowercased by the service) and uniquely
constrained; the password is stored only as a bcrypt hash. ``id`` is a
server-minted bigint identity (the database assigns it on insert), matching the
baseline ``users`` table and every FK target in the data model.

``revoked_sessions`` is the ``sid`` blacklist: each row revokes one session id
(shared by an access/refresh pair); presence means revoked. ``expires_at`` lets a
later cleanup job drop rows once the refresh token would have expired anyway.

These models are the single schema source ``alembic/env.py`` imports so
``--autogenerate`` diffs the real tables; they mirror migration ``0002_users``
plus ``0003`` (the onboarding flag and this blacklist).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Identity, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from floresu.core.orm import Base


class User(Base):
    """A human account. ``id`` is a server-minted bigint identity; never client-set."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Per-account onboarding completion. Server default false so new rows start
    # un-onboarded; the onboarding wizard flips it. Register sets it false
    # explicitly at the ORM level.
    has_completed_onboarding: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )


class RevokedSession(Base):
    """One revoked session id (``sid``); presence means revoked."""

    __tablename__ = "revoked_sessions"

    sid: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
