"""Skill ORM model: the curated per-user skill list.

``skills`` is a flat per-user table: a ``name`` (unique per user so a duplicate is
rejected, not silently reused), a ``sort_order`` for the curated ordering, and a
soft ``archived_at``. There is no stored usage count and no ``content_hash``: a
skill is not embeddable and its usage is derived on read from tag matches.

Per the data-model DDL this table carries no ``created_at``/``updated_at`` (unlike
the timestamped ``identity_variants`` sibling); it is a lightweight curated row
like ``tags``. This model is the single schema ``alembic/env.py`` imports so
``--autogenerate`` diffs the real table; it mirrors migration ``0008``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from floresu.core.orm import Base


class Skill(Base):
    """A curated per-user skill; its usage count is computed, never stored."""

    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # Soft archive: a non-null value means archived (dropped from active lists).
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # A name is unique per user, so a curated add of an existing name is a
        # conflict; the composite index also serves the per-user ordered list.
        UniqueConstraint("user_id", "name", name="uq_skills_user_id"),
        Index("ix_skills_user_id_sort_order", "user_id", "sort_order"),
    )
