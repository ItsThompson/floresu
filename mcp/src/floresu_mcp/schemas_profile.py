"""Lean profile-family read schemas (re-declared, not imported).

The ``profile_*`` tools are one family parameterized by ``kind``. The family spans
two backend storage patterns, so a read returns one of three shapes:

- the four ground-truth **source** kinds (role / project / certification /
  education) return a :class:`SourceSummary` (list) or a :class:`SourceRecord`
  with its typed :data:`SourceDetail` (get);
- **skill** returns a :class:`SkillRead`;
- **identity_variant** returns an :class:`IdentityVariantRead`.

:class:`ProfileKind` is the tool input discriminator; :class:`SourceKind` is the
narrower source discriminator carried on source reads (and shared with the search
graph). Outputs ignore unrecognized fields so a backend addition never breaks a
read. The cross-package contract tests (Ticket 22) keep every mirror honest.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class SourceKind(StrEnum):
    """The four ground-truth source kinds (the ``sources.kind`` discriminator)."""

    ROLE = "role"
    PROJECT = "project"
    CERTIFICATION = "certification"
    EDUCATION = "education"


class ProfileKind(StrEnum):
    """The kinds the ``profile_*`` family is parameterized by.

    The four source kinds plus the two non-source profile entities. ``reorder`` is
    not part of the read surface; ``identity_variant`` is unordered regardless.
    """

    ROLE = "role"
    PROJECT = "project"
    CERTIFICATION = "certification"
    EDUCATION = "education"
    SKILL = "skill"
    IDENTITY_VARIANT = "identity_variant"


class RoleDetail(BaseModel):
    """The role subtype detail joined into a role :class:`SourceRecord`."""

    model_config = ConfigDict(extra="ignore")

    company: str
    job_title: str
    title_aliases: list[str]
    location: str | None


class ProjectDetail(BaseModel):
    """The project subtype detail joined into a project :class:`SourceRecord`."""

    model_config = ConfigDict(extra="ignore")

    links: list[str]


class CertificationDetail(BaseModel):
    """The certification subtype detail joined into a cert :class:`SourceRecord`."""

    model_config = ConfigDict(extra="ignore")

    issuer: str
    credential_id: str | None


class EducationDetail(BaseModel):
    """The education subtype detail joined into an education :class:`SourceRecord`."""

    model_config = ConfigDict(extra="ignore")

    institution: str
    degree: str | None
    field: str | None


# The kind-specific detail on a single source read. The members carry disjoint
# required fields (company/job_title vs links vs issuer vs institution), so the
# union resolves deterministically from the backend's full projection.
SourceDetail = RoleDetail | ProjectDetail | CertificationDetail | EducationDetail


class SourceSummary(BaseModel):
    """Common-column source projection for a section list (no subtype join)."""

    model_config = ConfigDict(extra="ignore")

    id: int
    kind: SourceKind
    display_label: str
    date_start: date | None = None
    date_end: date | None = None
    summary: str | None = None
    sort_order: int
    archived_at: datetime | None = None


class SourceRecord(SourceSummary):
    """A single source with its typed subtype detail joined in."""

    detail: SourceDetail


class SkillRead(BaseModel):
    """A skill with its derived usage count (computed from tag matches, not stored)."""

    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    usage_count: int
    sort_order: int
    archived_at: datetime | None = None


class VariantContact(BaseModel):
    """A variant's contact fields; each is optional (a variant may omit any)."""

    model_config = ConfigDict(extra="ignore")

    email: str | None = None
    phone: str | None = None
    location: str | None = None


class VariantLink(BaseModel):
    """A labeled link (e.g. a portfolio or profile URL)."""

    model_config = ConfigDict(extra="ignore")

    label: str
    url: str


class IdentityVariantRead(BaseModel):
    """An identity variant with its default flag and archive state."""

    model_config = ConfigDict(extra="ignore")

    id: int
    label: str
    full_name: str
    contact: VariantContact
    links: list[VariantLink]
    is_default: bool
    archived_at: datetime | None = None


# What ``profile_list`` / ``profile_get`` return, keyed by the requested kind: the
# source shapes for the four ground-truth kinds, or the skill / variant shape.
ProfileSummary = SourceSummary | SkillRead | IdentityVariantRead
ProfileRecord = SourceRecord | SkillRead | IdentityVariantRead
