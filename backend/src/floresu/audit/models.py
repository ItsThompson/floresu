"""Audit-log ORM model: the append-only backbone of the feed and item history.

One row per content write. ``id`` is a server-minted monotonic bigint identity
that doubles as the SSE event id and the feed's ordering key. ``actor_type`` is
the native ``actor_type`` enum (human/agent) and ``actor_label`` names the agent
(null for a human, who renders as "you"). No field-level diff is stored: an
``action`` plus an optional ``summary`` and light ``metadata`` is the whole
record.

This model is the single schema source ``alembic/env.py`` imports so
``--autogenerate`` diffs the real table; it mirrors migration ``0004``. The
composite ``(user_id, id)`` index serves the per-user, newest-first feed and
item-history reads (Postgres scans it backward for ``ORDER BY id DESC``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, Text, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from floresu.core.actor import ActorType
from floresu.core.orm import Base

# The native ``actor_type`` enum, created by migration 0004 (``create_type=False``
# so table create/autogenerate never re-emits ``CREATE TYPE``). ``values_callable``
# pins the stored labels to the enum *values* ("human"/"agent"), not the member
# names, so the DB matches the Actor wire form.
ACTOR_TYPE_ENUM = postgresql.ENUM(
    ActorType,
    name="actor_type",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    create_type=False,
)


class AuditLog(Base):
    """One recorded content write. Append-only; rows are never updated."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    actor_type: Mapped[ActorType] = mapped_column(ACTOR_TYPE_ENUM, nullable=False)
    # Agent client_id / name; null for a human ("you").
    actor_label: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    # ``metadata`` is reserved on the declarative base (it is the MetaData object),
    # so the attribute is ``event_metadata`` mapped onto the ``metadata`` column.
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", postgresql.JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_audit_log_user_id_id", "user_id", "id"),)
