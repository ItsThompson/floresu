"""Lean resume read schemas (re-declared, not imported).

``resume_list`` returns a :class:`ResumeSummary` per resume (living and
application, the scalar columns without the document); ``resume_get`` returns a
:class:`ResumeRecord` that adds the full versioned :class:`ResumeDocument` (its
header, template, and ordered sections of library-ref and local items).

These are read projections: they carry the document shape faithfully but drop the
backend's write-time structural validators (the stored document is already
valid), and ignore unrecognized fields so a backend addition never breaks a read.
The cross-package contract tests (Ticket 22) keep every mirror honest.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ResumeKind(StrEnum):
    """A resume is either an evergreen living resume or a single application resume."""

    LIVING = "living"
    APPLICATION = "application"


class ResumeStatus(StrEnum):
    """Living resumes stay ``draft``; an application resume freezes to ``finalized``."""

    DRAFT = "draft"
    FINALIZED = "finalized"


class SectionKind(StrEnum):
    """The fixed set of resume section kinds."""

    WORK = "work"
    PROJECTS = "projects"
    EDUCATION = "education"
    SKILLS = "skills"
    CERTIFICATIONS = "certifications"
    SUMMARY = "summary"
    CUSTOM = "custom"


class IdentitySnapshotContact(BaseModel):
    """Frozen contact facts inlined on finalize; each field optional per variant."""

    model_config = ConfigDict(extra="ignore")

    email: str | None = None
    phone: str | None = None
    location: str | None = None


class IdentitySnapshotLink(BaseModel):
    """A labeled link inlined on finalize."""

    model_config = ConfigDict(extra="ignore")

    label: str
    url: str


class IdentitySnapshot(BaseModel):
    """Inlined, frozen identity facts a finalized resume carries in place of a reference."""

    model_config = ConfigDict(extra="ignore")

    full_name: str
    contact: IdentitySnapshotContact = Field(default_factory=IdentitySnapshotContact)
    links: list[IdentitySnapshotLink] = Field(default_factory=list)


class ResumeHeader(BaseModel):
    """The header: a living resume references a variant; a finalized one inlines a snapshot."""

    model_config = ConfigDict(extra="ignore")

    identity_variant_id: int | None = None
    identity_snapshot: IdentitySnapshot | None = None


class LocalItemSourceRefs(BaseModel):
    """Provenance carried on a local item so it can later be promoted to the library."""

    model_config = ConfigDict(extra="ignore")

    source_ids: list[int] = Field(default_factory=list)
    worklog_ids: list[int] = Field(default_factory=list)


class LibraryRefItem(BaseModel):
    """A resume item that references a canonical bulletpoint (text resolved on read)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    kind: Literal["library_ref"] = "library_ref"
    bullet_id: int


class LocalItem(BaseModel):
    """A resume-local item: a copy-on-write fork or a net-new inline item.

    Its ``text`` lives only on the resume, so it is never searchable and never
    embedded; ``forked_from_bullet_id`` is set when the item forks a canonical
    bullet and unset for a net-new inline item.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    kind: Literal["local"] = "local"
    text: str
    source_refs: LocalItemSourceRefs | None = None
    forked_from_bullet_id: int | None = None


# A resume item is a library reference or a resume-local item, discriminated on kind.
ResumeItem = Annotated[LibraryRefItem | LocalItem, Field(discriminator="kind")]


class ResumeSection(BaseModel):
    """One ordered section: an id-keyed items map plus an explicit order list."""

    model_config = ConfigDict(extra="ignore")

    id: str
    kind: SectionKind
    title: str
    item_order: list[str] = Field(default_factory=list)
    items: dict[str, ResumeItem] = Field(default_factory=dict)


class ResumeDocument(BaseModel):
    """The authoritative, versioned resume document."""

    model_config = ConfigDict(extra="ignore")

    schema_version: int
    header: ResumeHeader = Field(default_factory=ResumeHeader)
    template_id: str
    sections: list[ResumeSection] = Field(default_factory=list)


class ResumeSummary(BaseModel):
    """List projection: the scalar columns without the document."""

    model_config = ConfigDict(extra="ignore")

    id: int
    kind: ResumeKind
    status: ResumeStatus
    title: str
    revision: int
    schema_version: int
    job_application_id: int | None = None
    forked_from_resume_id: int | None = None
    archived_at: datetime | None = None
    updated_at: datetime


class ResumeRecord(ResumeSummary):
    """A single resume with its full, validated (upcast-on-read) document."""

    document: ResumeDocument
