"""Lean resume-write wire schemas (re-declared, not imported).

The write surface carries the resume creation contract and the document mutations.
:class:`ResumeCreateInput` mirrors the backend ``POST /resumes`` body exactly:
``kind`` chooses the result (living vs application) and is never inferred from
``source``; ``source`` is a discriminated union saying where the initial content
comes from; ``job_application_id`` is required only for an application resume. The
document write (:class:`ResumeUpdateInput`) reuses the resolved header and section
shapes; :class:`AddItemInput` mints no id (the server does);
:class:`ResumeReorderInput` addresses sections and items by id.

Every resume mutation carries the resume ``If-Match`` revision as a header (not a
body field); a stale revision is a recoverable conflict. :class:`FinalizeResult`
and :class:`RenderReference` are the terminal outputs (what was frozen/stored, and
where the PDF lives). The contract tests in ``contract/tests/`` keep every
mirror honest.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from floresu_mcp.schemas_resume import (
    LocalItemSourceRefs,
    ResumeHeader,
    ResumeKind,
    ResumeSection,
    ResumeStatus,
)


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


# Where the new resume's initial content comes from; ``kind`` (not this) decides
# living vs application.
ResumeSource = Annotated[
    BlankSource | FromResumeSource | DuplicateSource, Field(discriminator="mode")
]


class ResumeCreateInput(BaseModel):
    """The creation contract: ``kind`` sets the result; ``source`` seeds the content."""

    model_config = ConfigDict(extra="forbid")

    kind: ResumeKind
    source: ResumeSource
    # Required iff kind is application; rejected for living (the backend enforces both).
    job_application_id: int | None = None
    title: str | None = None
    # Optional override for a blank create; from_resume / duplicate copy the source.
    template_id: str | None = None


class ResumeUpdateInput(BaseModel):
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


# The item an add appends; the server mints its id. A library_ref or a local item.
ResumeItemInput = Annotated[LibraryRefItemInput | LocalItemInput, Field(discriminator="kind")]


class AddItemInput(BaseModel):
    """Append one item to a section; the server mints the item id."""

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(min_length=1)
    item: ResumeItemInput


class ResumeReorderInput(BaseModel):
    """Reorder sections and/or the items within sections, addressed by id.

    ``section_order`` is the full ordered list of section ids; each entry of
    ``item_orders`` maps a section id to the full ordered list of its item ids.
    At least one of the two must be provided.
    """

    model_config = ConfigDict(extra="forbid")

    section_order: list[str] | None = None
    item_orders: dict[str, list[str]] | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> ResumeReorderInput:
        if self.section_order is None and self.item_orders is None:
            raise ValueError("a reorder must provide section_order and/or item_orders")
        return self


class FinalizeResult(BaseModel):
    """The outcome of finalizing an application resume: what was frozen and stored."""

    model_config = ConfigDict(extra="ignore")

    resume_id: int
    status: ResumeStatus = ResumeStatus.FINALIZED
    pdf_object_key: str
    revision_no: int


class RenderReference(BaseModel):
    """Where a persisted resume PDF lives, plus a time-limited URL the user can open."""

    model_config = ConfigDict(extra="ignore")

    resume_id: int
    revision: int
    object_key: str
    download_url: str
