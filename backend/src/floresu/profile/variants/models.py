"""Identity-variant ORM model: labeled contact sets a resume header projects.

``identity_variants`` is a per-user table: a ``label`` (unique per user), a display
``full_name``, a ``contact`` JSONB object whose fields are each optional, a
``links`` JSONB array, an ``is_default`` flag, and a soft ``archived_at``. Unlike
skills, this table carries ``created_at``/``updated_at`` per the data-model DDL.

Exactly one default per user is enforced in the service (it flips the previous
default off in the same transaction), not by a database constraint, so the flag is
a plain boolean here. This model is the single schema ``alembic/env.py`` imports so
``--autogenerate`` diffs the real table; it mirrors migration ``0008``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from floresu.core.orm import Base


class IdentityVariant(Base):
    """A labeled contact set; exactly one is the user's default at any time."""

    __tablename__ = "identity_variants"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    # ``{ email?, phone?, location? }``: each field optional per variant.
    contact: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False)
    # ``[ { label, url } ]``.
    links: Mapped[list[dict[str, Any]]] = mapped_column(postgresql.JSONB, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # Soft archive: a non-null value means archived (dropped from active lists).
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # A label is unique per user; the composite index also serves the per-user
        # list (variants are unordered, listed by label).
        UniqueConstraint("user_id", "label", name="uq_identity_variants_user_id"),
    )
