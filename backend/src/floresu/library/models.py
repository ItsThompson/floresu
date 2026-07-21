"""Library ORM models: canonical bulletpoints and the two provenance edges.

``bulletpoints`` is the canonical, reusable framing row: a ``text``, a
``content_hash`` over that text that gates re-embedding, an optimistic
``revision`` token, and the soft ``archived_at``. Only canonical bullets live
here; a resume-local copy-on-write fork lives inline in the resume document, not
in this table, which keeps outputs out of the searchable corpus by construction.

A bullet frames ground-truth items through two many-to-many edges: ``bullet_source``
(the bullet frames a source directly) and ``bullet_worklog`` (the bullet frames a
worklog entry). Together with ``worklog_source`` (owned by the worklog domain)
they are the three joins of the provenance DAG. Both edge tables are pure edges (a
composite primary key, no surrogate id) and cascade on either endpoint's delete,
so archiving is a soft state on the bullet while a hard delete of a bullet, a
source, or a worklog entry removes only its edges.

These models are the single schema ``alembic/env.py`` imports so ``--autogenerate``
diffs the real tables; they mirror migration ``0008``. ``text`` is the bullet's
searchable text, so it stays plain ``TEXT`` for the full-text indexes a later
slice adds.
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
    func,
)
from sqlalchemy import text as sql  # aliased: the column below is named ``text``
from sqlalchemy.orm import Mapped, mapped_column

from floresu.core.orm import Base


class Bulletpoint(Base):
    """A canonical, reusable bulletpoint: one framing of ground-truth sources."""

    __tablename__ = "bulletpoints"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Hash over the bullet text; the service recomputes it on edit and the
    # embedding worker compares it to gate re-embedding. Never null: set on create.
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # Optimistic-concurrency token for scope=everywhere edits guarded by If-Match.
    # This table creates it; the guarded edit path that increments it lands later.
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sql("1"))
    # Soft archive: a non-null value means archived (dropped from library reads).
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # Serves the per-user library list, newest-first (scanned backward for id DESC).
        Index("ix_bulletpoints_user_id_id", "user_id", "id"),
        # Lexical full-text search over the bullet text. The explicit 'english'
        # regconfig keeps to_tsvector immutable, so the GIN expression index is
        # valid. Written in Postgres's canonical rendered form so it round-trips
        # through reflection and autogenerate emits no diff. Mirrors migration 0010.
        Index(
            "ix_bulletpoints_fts",
            sql("to_tsvector('english'::regconfig, text)"),
            postgresql_using="gin",
        ),
    )


class BulletSource(Base):
    """M:N edge: a bulletpoint frames a source directly (provenance DAG)."""

    __tablename__ = "bullet_source"

    bullet_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("bulletpoints.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )


class BulletWorklog(Base):
    """M:N edge: a bulletpoint frames a worklog entry (provenance DAG)."""

    __tablename__ = "bullet_worklog"

    bullet_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("bulletpoints.id", ondelete="CASCADE"), primary_key=True
    )
    worklog_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("worklog_entries.id", ondelete="CASCADE"), primary_key=True
    )
