"""Worklog ORM models: entries, tags, and the two many-to-many attachment tables.

``worklog_entries`` is the ground-truth timeline row: a title, an ``entry_date``,
an optional ``description``, and a ``content_hash`` over the embeddable text that
gates re-embedding. An entry attaches to zero, one, or many ``sources`` through
``worklog_source`` and carries zero or more ``tags`` through ``worklog_tag``.

Tags are normalized into their own per-user table (``UNIQUE (user_id, label)``),
so a rename or a reuse stays consistent and counts are cheap. Tag color is not a
column: it is derived deterministically from the label by the shared
``colorForName`` utility, so it is always stable and never stored.

Both attachment tables are pure edges (a composite primary key, no surrogate id)
and cascade on either endpoint's delete, so archiving is a soft state on the entry
while a hard delete of an entry, a source, or a tag removes only its edges.

These models are the single schema ``alembic/env.py`` imports so ``--autogenerate``
diffs the real tables; they mirror migration ``0007``. ``title`` and
``description`` are the entry's searchable text, so they stay plain ``TEXT`` for
the full-text indexes a later slice adds.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from floresu.core.orm import Base


class WorklogEntry(Base):
    """A timestamped worklog entry: the ground-truth record of a unit of work."""

    __tablename__ = "worklog_entries"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Hash over title + description; the service recomputes it on edit and the
    # embedding worker compares it to gate re-embedding. Never null: set on create.
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # Soft archive: a non-null value means archived (dropped from active reads).
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # Serves the per-user timeline read, ordered by date.
        Index("ix_worklog_entries_user_id_entry_date", "user_id", "entry_date"),
    )


class Tag(Base):
    """A per-user free-text label; reused across entries, unique per user."""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        # A label is unique per user, so a reuse resolves to the existing row and
        # the composite index also serves the per-user tag list (ordered by label).
        UniqueConstraint("user_id", "label", name="uq_tags_user_id"),
    )


class WorklogSource(Base):
    """M:N edge attaching a worklog entry to a source (usually one, many allowed)."""

    __tablename__ = "worklog_source"

    worklog_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("worklog_entries.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )


class WorklogTag(Base):
    """M:N edge attaching a tag to a worklog entry; removing it never drops the tag."""

    __tablename__ = "worklog_tag"

    worklog_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("worklog_entries.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
