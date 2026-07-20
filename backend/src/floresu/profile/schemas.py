"""Wire schemas for sources: the write union, the read shapes, and reorder input.

Writes are a discriminated union on ``kind`` (:data:`SourceWrite`), so each kind
validates its own required fields (a role needs company and job title; a
certification needs an issuer) and the API cannot accept a payload whose fields
disagree with its kind. The same shape backs create and full-representation
update; ``kind`` is immutable, so update rejects a body whose kind differs from
the stored row.

Reads come in two shapes, matching the supertable access pattern: a
:class:`SourceSummary` (common columns only) for section lists, and a
:class:`SourceRecord` that adds the typed ``detail`` for a single item. IDs,
timestamps, and ``sort_order`` are server-owned and never accepted on a write.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from floresu.profile.models import (
    Certification,
    Education,
    Project,
    Role,
    SourceKind,
    SourceSubtype,
)

# Common columns clients supply on every write; excluded when projecting a write
# onto its subtype row (the leftover fields are exactly the kind-specific columns).
_COMMON_WRITE_FIELDS = frozenset({"kind", "display_label", "date_start", "date_end", "summary"})


class _SourceWriteBase(BaseModel):
    """Common columns every source write carries."""

    model_config = ConfigDict(extra="forbid")

    display_label: str = Field(min_length=1)
    date_start: date | None = None
    date_end: date | None = None
    summary: str | None = None


class RoleWrite(_SourceWriteBase):
    kind: Literal[SourceKind.ROLE] = SourceKind.ROLE
    company: str = Field(min_length=1)
    job_title: str = Field(min_length=1)
    title_aliases: list[str] = Field(default_factory=list)
    location: str | None = None


class ProjectWrite(_SourceWriteBase):
    kind: Literal[SourceKind.PROJECT] = SourceKind.PROJECT
    links: list[str] = Field(default_factory=list)


class CertificationWrite(_SourceWriteBase):
    kind: Literal[SourceKind.CERTIFICATION] = SourceKind.CERTIFICATION
    issuer: str = Field(min_length=1)
    credential_id: str | None = None


class EducationWrite(_SourceWriteBase):
    kind: Literal[SourceKind.EDUCATION] = SourceKind.EDUCATION
    institution: str = Field(min_length=1)
    degree: str | None = None
    field: str | None = None


# The create/update body: FastAPI validates the payload against the member picked
# by ``kind``, so kind-specific required fields are enforced at the boundary.
SourceWriteMember = RoleWrite | ProjectWrite | CertificationWrite | EducationWrite
SourceWrite = Annotated[SourceWriteMember, Field(discriminator="kind")]


def subtype_values(write: SourceWriteMember) -> dict[str, Any]:
    """The kind-specific column values for a write (common columns removed)."""
    return write.model_dump(exclude=set(_COMMON_WRITE_FIELDS))


class RoleDetail(BaseModel):
    company: str
    job_title: str
    title_aliases: list[str]
    location: str | None


class ProjectDetail(BaseModel):
    links: list[str]


class CertificationDetail(BaseModel):
    issuer: str
    credential_id: str | None


class EducationDetail(BaseModel):
    institution: str
    degree: str | None
    field: str | None


SourceDetail = RoleDetail | ProjectDetail | CertificationDetail | EducationDetail


class SourceSummary(BaseModel):
    """Common-column projection for section lists (no subtype join)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: SourceKind
    display_label: str
    date_start: date | None
    date_end: date | None
    summary: str | None
    sort_order: int
    archived_at: datetime | None


class SourceRecord(SourceSummary):
    """A single source with its typed subtype detail joined in."""

    detail: SourceDetail


class ReorderRequest(BaseModel):
    """A section reorder: the full ordered id list for one kind."""

    model_config = ConfigDict(extra="forbid")

    kind: SourceKind
    source_ids: list[int] = Field(min_length=1)


# kind -> (subtype ORM class, detail schema). The service reads this to build the
# subtype row on write and the typed detail on read, so a new kind is a table plus
# one entry here rather than a branch in the service.
KIND_SPECS: dict[SourceKind, tuple[type[SourceSubtype], type[SourceDetail]]] = {
    SourceKind.ROLE: (Role, RoleDetail),
    SourceKind.PROJECT: (Project, ProjectDetail),
    SourceKind.CERTIFICATION: (Certification, CertificationDetail),
    SourceKind.EDUCATION: (Education, EducationDetail),
}


def to_summary(source: Any) -> SourceSummary:
    """Project a ``sources`` ORM row onto the common-column read shape."""
    return SourceSummary.model_validate(source)


def to_record(source: Any, subtype: SourceSubtype) -> SourceRecord:
    """Join a base row and its subtype row into the typed read shape."""
    _, detail_model = KIND_SPECS[source.kind]
    detail = detail_model.model_validate(subtype, from_attributes=True)
    return SourceRecord(
        id=source.id,
        kind=source.kind,
        display_label=source.display_label,
        date_start=source.date_start,
        date_end=source.date_end,
        summary=source.summary,
        sort_order=source.sort_order,
        archived_at=source.archived_at,
        detail=detail,
    )
