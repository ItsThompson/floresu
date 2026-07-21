"""Wire schemas for resumes: the creation contract, writes, and read shapes.

The creation contract is explicit (:class:`ResumeCreateRequest`): ``kind`` chooses
the result (living vs application) and is never inferred from ``source``; ``source``
is a discriminated union saying where the initial content comes from (blank, from
another resume, or a faithful duplicate); ``job_application_id`` is required when
``kind`` is application and forbidden when it is living. The document write
(:class:`ResumeUpdate`) carries the authoritative content minus the server-owned
``schema_version``; the add-item body mints no id (the server does). Reads come in
two shapes: a :class:`ResumeSummary` for lists and a :class:`ResumeRecord` that
adds the full validated document. IDs, timestamps, ``schema_version``, ``status``,
and ``revision`` are server-owned and never accepted on a write.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from floresu.resumes.document import (
    LocalItemSourceRefs,
    ResumeDocument,
    ResumeHeader,
    ResumeSection,
)
from floresu.resumes.models import Resume, ResumeKind, ResumeStatus


class BlankSource(BaseModel):
    """Seed an empty document."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["blank"] = "blank"


class FromResumeSource(BaseModel):
    """Seed content from an existing resume (the copies may later diverge in shape)."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["from_resume"] = "from_resume"
    from_resume_id: int


class DuplicateSource(BaseModel):
    """Make a faithful copy of an existing resume."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["duplicate"] = "duplicate"
    duplicate_id: int


ResumeSource = Annotated[
    BlankSource | FromResumeSource | DuplicateSource, Field(discriminator="mode")
]


class ResumeCreateRequest(BaseModel):
    """The creation contract: ``kind`` sets the result; ``source`` seeds the content."""

    model_config = ConfigDict(extra="forbid")

    kind: ResumeKind
    source: ResumeSource
    # Required iff kind is application; rejected for living (the service enforces
    # both, and the table CHECK backstops the living case).
    job_application_id: int | None = None
    title: str | None = None
    # Optional override for a blank create; from_resume / duplicate copy the source.
    template_id: str | None = None


class ResumeUpdate(BaseModel):
    """The full-document write: the authoritative content the single writer persists."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    template_id: str = Field(min_length=1)
    header: ResumeHeader = Field(default_factory=ResumeHeader)
    sections: list[ResumeSection] = Field(default_factory=list)


class LibraryRefItemInput(BaseModel):
    """Add an item that references a canonical bulletpoint."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["library_ref"] = "library_ref"
    bullet_id: int


class LocalItemInput(BaseModel):
    """Add a net-new inline item; its text lives only on the resume."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["local"] = "local"
    text: str = Field(min_length=1)
    source_refs: LocalItemSourceRefs | None = None


ResumeItemInput = Annotated[LibraryRefItemInput | LocalItemInput, Field(discriminator="kind")]


class AddItemRequest(BaseModel):
    """Append one item to a section; the server mints the item id."""

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(min_length=1)
    item: ResumeItemInput


class ResumeReorderRequest(BaseModel):
    """Reorder sections and/or the items within sections, addressed by id.

    ``section_order`` is the full ordered list of section ids; each entry of
    ``item_orders`` maps a section id to the full ordered list of its item ids.
    Both are permutations of their current sets (the service rejects a partial or
    duplicated list), so a reorder never addresses an item by array index and never
    collides. At least one of the two must be provided.
    """

    model_config = ConfigDict(extra="forbid")

    section_order: list[str] | None = None
    item_orders: dict[str, list[str]] | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> ResumeReorderRequest:
        if self.section_order is None and self.item_orders is None:
            raise ValueError("a reorder must provide section_order and/or item_orders")
        return self


class ResumeSummary(BaseModel):
    """List projection: the scalar columns without the document."""

    model_config = ConfigDict(extra="forbid")

    id: int
    kind: ResumeKind
    status: ResumeStatus
    title: str
    revision: int
    schema_version: int
    job_application_id: int | None
    forked_from_resume_id: int | None
    archived_at: datetime | None
    updated_at: datetime


class ResumeRecord(ResumeSummary):
    """A single resume with its full, validated (upcast-on-read) document."""

    document: ResumeDocument


def to_summary(resume: Resume) -> ResumeSummary:
    """Project a ``resumes`` row onto the list shape (no document)."""
    return ResumeSummary(
        id=resume.id,
        kind=resume.kind,
        status=resume.status,
        title=resume.title,
        revision=resume.revision,
        schema_version=resume.schema_version,
        job_application_id=resume.job_application_id,
        forked_from_resume_id=resume.forked_from_resume_id,
        archived_at=resume.archived_at,
        updated_at=resume.updated_at,
    )


def to_record(resume: Resume, document: ResumeDocument) -> ResumeRecord:
    """Join a row and its validated document into the single-read shape."""
    return ResumeRecord(**to_summary(resume).model_dump(), document=document)
