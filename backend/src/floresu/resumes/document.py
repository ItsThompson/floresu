"""The versioned resume document: the JSONB shape, its validators, and pure helpers.

The document is the authoritative content of a resume. It is a versioned structure
(``schema_version`` mirrors the row column): a header projecting an identity, a
selected ``template_id``, and ordered sections. Each section stores its items as an
id-keyed map plus an explicit ``item_order`` list, so storage is order-invariant
and a reorder never addresses an item by array index and never collides. An item
is a discriminated union on ``kind``: a :class:`LibraryRefItem` (a reference to a
canonical bulletpoint, resolved on read) or a :class:`LocalItem` (a resume-local
inline fork or net-new item whose text lives only here, so it is never searchable
and never embedded).

Validation is a boundary contract: constructing a :class:`ResumeDocument` enforces
that every section id is unique, every item's map key equals its own id, and
``item_order`` is a permutation of the items map (no missing id, no stray id, no
duplicate). Malformed input is rejected before it reaches the service.

The pure helpers here (:func:`referenced_bullet_ids`, :func:`resolve_document`)
carry no I/O: the service supplies the resolved bullet texts and these functions
compute the referenced-bullet set and the fully resolved snapshot document.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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

    model_config = ConfigDict(extra="forbid")

    email: str | None = None
    phone: str | None = None
    location: str | None = None


class IdentitySnapshotLink(BaseModel):
    """A labeled link inlined on finalize."""

    model_config = ConfigDict(extra="forbid")

    label: str
    url: str


class IdentitySnapshot(BaseModel):
    """Inlined, frozen identity facts a finalized resume carries in place of a reference."""

    model_config = ConfigDict(extra="forbid")

    full_name: str
    contact: IdentitySnapshotContact = Field(default_factory=IdentitySnapshotContact)
    links: list[IdentitySnapshotLink] = Field(default_factory=list)


class ResumeHeader(BaseModel):
    """The header: a living resume references a variant; a finalized one inlines a snapshot."""

    model_config = ConfigDict(extra="forbid")

    # Resolved on preview for a living/draft resume.
    identity_variant_id: int | None = None
    # Inlined, frozen on finalize (set by the finalize routine).
    identity_snapshot: IdentitySnapshot | None = None


class LocalItemSourceRefs(BaseModel):
    """Provenance carried on a local item so it can later be promoted to the library."""

    model_config = ConfigDict(extra="forbid")

    source_ids: list[int] = Field(default_factory=list)
    worklog_ids: list[int] = Field(default_factory=list)


class LibraryRefItem(BaseModel):
    """An item that references a canonical bulletpoint; the text is resolved on read."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: Literal["library_ref"] = "library_ref"
    bullet_id: int


class LocalItem(BaseModel):
    """A resume-local item: a copy-on-write fork or a net-new inline item.

    Its ``text`` lives only here, so it is never searchable and never embedded.
    ``forked_from_bullet_id`` is set when the item is a fork of a canonical bullet
    (the copy-on-write path sets it); a net-new inline item leaves it unset.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: Literal["local"] = "local"
    text: str = Field(min_length=1)
    source_refs: LocalItemSourceRefs | None = None
    forked_from_bullet_id: int | None = None


ResumeItem = Annotated[LibraryRefItem | LocalItem, Field(discriminator="kind")]


class ResumeSection(BaseModel):
    """One ordered section: an id-keyed items map plus an explicit order list."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: SectionKind
    title: str
    item_order: list[str] = Field(default_factory=list)
    items: dict[str, LibraryRefItem | LocalItem] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_items_and_order(self) -> ResumeSection:
        """Every map key equals its item id, and ``item_order`` is a permutation of the keys."""
        for key, item in self.items.items():
            if item.id != key:
                raise ValueError(f"item map key {key!r} does not match item id {item.id!r}")
        if len(self.item_order) != len(set(self.item_order)):
            raise ValueError("item_order contains duplicate ids")
        if set(self.item_order) != set(self.items):
            raise ValueError("item_order must list every item id exactly once")
        return self


class ResumeDocument(BaseModel):
    """The authoritative, versioned resume document."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int
    header: ResumeHeader = Field(default_factory=ResumeHeader)
    template_id: str = Field(min_length=1)
    sections: list[ResumeSection] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_unique_section_ids(self) -> ResumeDocument:
        section_ids = [section.id for section in self.sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("sections contain duplicate ids")
        return self


def referenced_bullet_ids(document: ResumeDocument) -> list[int]:
    """The distinct canonical bullet ids the live document references, first-seen order."""
    seen: dict[int, None] = {}
    for section in document.sections:
        for item_id in section.item_order:
            item = section.items[item_id]
            if isinstance(item, LibraryRefItem):
                seen.setdefault(item.bullet_id, None)
    return list(seen)


def resolve_document(document: ResumeDocument, bullet_texts: dict[int, str]) -> ResumeDocument:
    """Return a fully resolved copy: every library_ref item inlined as a local item.

    A ``library_ref`` item becomes a :class:`LocalItem` carrying the bullet text
    resolved at this moment, with ``forked_from_bullet_id`` retained for provenance.
    A ``local`` item is copied unchanged. The resolved document therefore holds zero
    references, so a later library edit can never rewrite it: this is what a
    revision snapshot stores.
    """
    resolved_sections: list[ResumeSection] = []
    for section in document.sections:
        resolved_items: dict[str, LibraryRefItem | LocalItem] = {}
        for item_id, item in section.items.items():
            if isinstance(item, LibraryRefItem):
                resolved_items[item_id] = LocalItem(
                    id=item.id,
                    text=bullet_texts[item.bullet_id],
                    forked_from_bullet_id=item.bullet_id,
                )
            else:
                resolved_items[item_id] = item.model_copy(deep=True)
        resolved_sections.append(
            ResumeSection(
                id=section.id,
                kind=section.kind,
                title=section.title,
                item_order=list(section.item_order),
                items=resolved_items,
            )
        )
    return ResumeDocument(
        schema_version=document.schema_version,
        header=document.header.model_copy(deep=True),
        template_id=document.template_id,
        sections=resolved_sections,
    )
