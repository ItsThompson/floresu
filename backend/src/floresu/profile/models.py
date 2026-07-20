"""Sources ORM models: the class-table-inheritance supertable and its subtypes.

``sources`` is the base table: it holds the common columns every source shares
(``display_label``, dates, ``summary``, ``sort_order``, ``archived_at``) plus the
``kind`` discriminator, and it is the single polymorphic FK target worklog and
bullets attach to. Its ``UNIQUE (id, kind)`` lets each subtype bind ``kind`` in a
composite foreign key so a subtype row can never disagree with which subtype it
is: the per-subtype ``kind`` CHECK pins the value and the composite FK enforces it
against the base row.

One subtype table per kind (``roles`` / ``projects`` / ``certifications`` /
``education``) holds only that kind's columns. A list read that needs common
fields hits ``sources`` alone; a typed-detail read joins the one subtype table.

These models are the single schema source ``alembic/env.py`` imports so
``--autogenerate`` diffs the real tables; they mirror migration ``0006``.
``display_label``, ``summary``, and the role company/title columns are the source
text that becomes part of the searchable corpus, so they stay plain ``TEXT`` for
the full-text indexes a later slice adds.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from floresu.core.orm import Base


class SourceKind(StrEnum):
    """The four ground-truth source kinds; the ``sources.kind`` discriminator."""

    ROLE = "role"
    PROJECT = "project"
    CERTIFICATION = "certification"
    EDUCATION = "education"


# The native ``source_kind`` enum, created by migration 0006 (``create_type=False``
# so table create/autogenerate never re-emits ``CREATE TYPE``). ``values_callable``
# pins the stored labels to the enum *values*, matching the wire form. The one
# instance is shared by the base column and all four subtype columns.
SOURCE_KIND_ENUM = postgresql.ENUM(
    SourceKind,
    name="source_kind",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    create_type=False,
)


class Source(Base):
    """The supertable base row: common columns plus the ``kind`` discriminator."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[SourceKind] = mapped_column(SOURCE_KIND_ENUM, nullable=False)
    # Denormalized human label; drives lists and search attribution.
    display_label: Mapped[str] = mapped_column(Text, nullable=False)
    date_start: Mapped[date | None] = mapped_column(Date)
    # Null means ongoing; rendered "Present" downstream.
    date_end: Mapped[date | None] = mapped_column(Date)
    summary: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # Soft archive: a non-null value means archived (dropped from active lists).
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # Lets the subtypes bind ``kind`` via a composite FK to ``(id, kind)``.
        UniqueConstraint("id", "kind", name="uq_sources_id_kind"),
        # Serves the per-user, per-kind ordered section list.
        Index("ix_sources_user_id_kind_sort_order", "user_id", "kind", "sort_order"),
    )


def _kind_locked_args(table: str, kind: SourceKind) -> tuple[CheckConstraint, ForeignKeyConstraint]:
    """The CHECK + composite FK that lock a subtype row to one ``sources.kind``.

    The CHECK pins this table's ``kind`` to a single value and the composite FK
    binds ``(source_id, kind)`` to ``sources(id, kind)``, so a subtype row can
    exist only for a base row of the matching kind and the two can never diverge.
    """
    return (
        # The ``ck`` naming convention wraps this to ``ck_<table>_kind``; passing the
        # full name here would double the prefix.
        CheckConstraint(f"kind = '{kind.value}'", name="kind"),
        ForeignKeyConstraint(
            ["source_id", "kind"],
            ["sources.id", "sources.kind"],
            ondelete="CASCADE",
            name=f"fk_{table}_source_id_sources",
        ),
    )


class Role(Base):
    """Work-experience subtype: company, job title, aliases, location."""

    __tablename__ = "roles"

    source_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[SourceKind] = mapped_column(SOURCE_KIND_ENUM, nullable=False)
    company: Mapped[str] = mapped_column(Text, nullable=False)
    job_title: Mapped[str] = mapped_column(Text, nullable=False)
    title_aliases: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    location: Mapped[str | None] = mapped_column(Text)

    __table_args__ = _kind_locked_args("roles", SourceKind.ROLE)


class Project(Base):
    """Project subtype: reference links (the timeframe/description use the base)."""

    __tablename__ = "projects"

    source_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[SourceKind] = mapped_column(SOURCE_KIND_ENUM, nullable=False)
    links: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(Text), nullable=False, server_default=text("'{}'")
    )

    __table_args__ = _kind_locked_args("projects", SourceKind.PROJECT)


class Certification(Base):
    """Certification subtype: issuer and optional credential id (date is the base)."""

    __tablename__ = "certifications"

    source_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[SourceKind] = mapped_column(SOURCE_KIND_ENUM, nullable=False)
    issuer: Mapped[str] = mapped_column(Text, nullable=False)
    credential_id: Mapped[str | None] = mapped_column(Text)

    __table_args__ = _kind_locked_args("certifications", SourceKind.CERTIFICATION)


class Education(Base):
    """Education subtype: institution, degree, and field of study."""

    __tablename__ = "education"

    source_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[SourceKind] = mapped_column(SOURCE_KIND_ENUM, nullable=False)
    institution: Mapped[str] = mapped_column(Text, nullable=False)
    degree: Mapped[str | None] = mapped_column(Text)
    field: Mapped[str | None] = mapped_column(Text)

    __table_args__ = _kind_locked_args("education", SourceKind.EDUCATION)


# One subtype ORM class per kind. The service builds the base row and the matching
# subtype row from this map, so adding a kind is a table + entry, not a branch.
SUBTYPE_MODELS: dict[SourceKind, type[Role | Project | Certification | Education]] = {
    SourceKind.ROLE: Role,
    SourceKind.PROJECT: Project,
    SourceKind.CERTIFICATION: Certification,
    SourceKind.EDUCATION: Education,
}

# The subtype row that pairs with a base row of a given kind.
SourceSubtype = Role | Project | Certification | Education
