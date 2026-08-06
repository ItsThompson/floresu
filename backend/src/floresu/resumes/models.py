"""Resume ORM models: the JSONB-authoritative resume and its write-derived index.

``resumes`` is the Output layer's authoritative row: the full content lives in the
``document`` JSONB, and a few scalar columns are re-derived on every write by the
single service writer so they cannot drift (``title``, ``schema_version``, the
optimistic ``revision`` token). ``kind`` (living | application) is chosen at
creation and never inferred; ``status`` is ``draft`` for every living resume and
moves to ``finalized`` only for an application resume (the finalize routine lands
later). ``forked_from_resume_id`` records the provenance of a fork/duplicate;
``job_application_id`` is the single, unique 1:1 link an application resume carries
(a ``CHECK`` forbids a living resume from linking one).

``resume_bullet_ref`` is write-derived: the service reindexes it on every save to
exactly the canonical bullets the live document references, so "used in N" is a
cheap count. ``resume_revisions`` is append-only (keep-all): every save stores a
fully resolved snapshot (references resolved to text at that moment) so a later
library edit can never rewrite the past.

``job_applications`` is created before ``resumes`` because ``resumes`` holds the
FK; the link is one-directional, so there is no circular dependency. These models
are the single schema ``alembic/env.py`` imports so
``--autogenerate`` diffs the real tables; they mirror migration ``0010``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
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


class ResumeKind(StrEnum):
    """A resume is either an evergreen living resume or a single application resume."""

    LIVING = "living"
    APPLICATION = "application"


class ResumeStatus(StrEnum):
    """Living resumes stay ``draft``; an application resume freezes to ``finalized``."""

    DRAFT = "draft"
    FINALIZED = "finalized"


class JobApplicationStatus(StrEnum):
    """A job application is ``added`` then ``submitted`` (submit finalizes its resume)."""

    ADDED = "added"
    SUBMITTED = "submitted"


# Native enums, created explicitly in migration 0010 (``create_type=False`` so a
# table create / autogenerate never re-emits ``CREATE TYPE``). ``values_callable``
# pins the stored labels to the enum *values*, matching the wire form.
RESUME_KIND_ENUM = postgresql.ENUM(
    ResumeKind,
    name="resume_kind",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    create_type=False,
)
RESUME_STATUS_ENUM = postgresql.ENUM(
    ResumeStatus,
    name="resume_status",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    create_type=False,
)
JOB_APPLICATION_STATUS_ENUM = postgresql.ENUM(
    JobApplicationStatus,
    name="job_application_status",
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    create_type=False,
)


class JobApplication(Base):
    """A lightweight relational job application; its 1:1 resume link lives on ``resumes``."""

    __tablename__ = "job_applications"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    company: Mapped[str] = mapped_column(Text, nullable=False)
    role_title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[JobApplicationStatus] = mapped_column(
        JOB_APPLICATION_STATUS_ENUM, nullable=False, server_default=JobApplicationStatus.ADDED.value
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # Serves the per-user, newest-first application list (scanned backward).
        Index("ix_job_applications_user_id_id", "user_id", "id"),
    )


class Resume(Base):
    """A JSONB-authoritative resume: the document plus write-derived scalar columns."""

    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[ResumeKind] = mapped_column(RESUME_KIND_ENUM, nullable=False)
    status: Mapped[ResumeStatus] = mapped_column(
        RESUME_STATUS_ENUM, nullable=False, server_default=ResumeStatus.DRAFT.value
    )
    # Derived from the document by the single writer; never client-set directly.
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # Shape version of ``document``; re-derived to CURRENT on every write.
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    # Optimistic-concurrency token; a write carries the expected value via If-Match
    # and a successful write increments it.
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    # The authoritative content: the resolved-on-read document shape.
    document: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False)
    # Provenance of a fork/duplicate; set to the source resume id (SET NULL on its delete).
    forked_from_resume_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("resumes.id", ondelete="SET NULL")
    )
    # The 1:1 link to a job application; non-null only for an application resume.
    job_application_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("job_applications.id", ondelete="SET NULL")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # One resume per job application (1:1); many NULLs allowed (unlinked resumes).
        UniqueConstraint("job_application_id", name="uq_resumes_job_application_id"),
        # Only an application resume may link a job application.
        CheckConstraint(
            "job_application_id IS NULL OR kind = 'application'", name="job_application_kind"
        ),
        # Serves the per-user, newest-first resume list (scanned backward for id DESC).
        Index("ix_resumes_user_id_id", "user_id", "id"),
    )


class ResumeBulletRef(Base):
    """Write-derived: which canonical bullets a resume references (reindexed each save)."""

    __tablename__ = "resume_bullet_ref"

    resume_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("resumes.id", ondelete="CASCADE"), primary_key=True
    )
    bullet_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("bulletpoints.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (
        # Powers the "used in N" count: COUNT(*) WHERE bullet_id = ?.
        Index("ix_resume_bullet_ref_bullet_id", "bullet_id"),
    )


class ResumeRevision(Base):
    """Append-only (keep-all): a fully resolved snapshot of the document per save."""

    __tablename__ = "resume_revisions"

    resume_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("resumes.id", ondelete="CASCADE"), primary_key=True
    )
    revision_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    # FULLY RESOLVED at this save: library_ref items resolved to inline text, so a
    # later library edit never rewrites this past snapshot.
    document: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    # R2 object key of the rendered PDF for this revision; set by the render path.
    pdf_object_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
