"""Lean profile-family write schemas (re-declared, not imported).

The ``profile_*`` write tools are one family parameterized by ``kind``, mirroring
the read family. A create/update body is a discriminated union on ``kind``
(:data:`ProfileWriteInput`) so each kind validates its own required fields (a role
needs a company and job title, a certification an issuer, a skill only a name), and
the tool cannot accept a payload whose fields disagree with its kind. The four
ground-truth source kinds carry the ``kind`` discriminator to the backend
``/sources`` endpoint (which is itself a discriminated union on kind); skill and
identity_variant drop it before hitting their own endpoints (their backend write
bodies carry no kind).

Inputs mirror the backend write bodies field-for-field and forbid unknown fields;
server-owned columns (id, timestamps, ``sort_order``, ``archived_at``,
``usage_count``) are never accepted on a write. The cross-package contract tests
(Ticket 22) keep every mirror honest.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from floresu_mcp.schemas_profile import ProfileKind


class _SourceWriteBase(BaseModel):
    """Common columns every source write carries."""

    model_config = ConfigDict(extra="forbid")

    display_label: str = Field(min_length=1)
    date_start: date | None = None
    date_end: date | None = None
    summary: str | None = None


class RoleWriteInput(_SourceWriteBase):
    """A role source: an employer and a job title (plus optional aliases/location)."""

    kind: Literal[ProfileKind.ROLE] = ProfileKind.ROLE
    company: str = Field(min_length=1)
    job_title: str = Field(min_length=1)
    title_aliases: list[str] = Field(default_factory=list)
    location: str | None = None


class ProjectWriteInput(_SourceWriteBase):
    """A project source: optional reference links."""

    kind: Literal[ProfileKind.PROJECT] = ProfileKind.PROJECT
    links: list[str] = Field(default_factory=list)


class CertificationWriteInput(_SourceWriteBase):
    """A certification source: an issuer and an optional credential id."""

    kind: Literal[ProfileKind.CERTIFICATION] = ProfileKind.CERTIFICATION
    issuer: str = Field(min_length=1)
    credential_id: str | None = None


class EducationWriteInput(_SourceWriteBase):
    """An education source: an institution, an optional degree and field."""

    kind: Literal[ProfileKind.EDUCATION] = ProfileKind.EDUCATION
    institution: str = Field(min_length=1)
    degree: str | None = None
    field: str | None = None


class SkillWriteInput(BaseModel):
    """The skill create/rename body: a skill is defined by its curated ``name``."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal[ProfileKind.SKILL] = ProfileKind.SKILL
    name: str = Field(min_length=1)


class VariantContactInput(BaseModel):
    """A variant's contact fields; each is optional (a variant may omit any)."""

    model_config = ConfigDict(extra="forbid")

    email: str | None = None
    phone: str | None = None
    location: str | None = None


class VariantLinkInput(BaseModel):
    """A labeled link (e.g. a portfolio or profile URL)."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    url: str = Field(min_length=1)


class IdentityVariantWriteInput(BaseModel):
    """The identity-variant create/update body: label, name, contact, links, default."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal[ProfileKind.IDENTITY_VARIANT] = ProfileKind.IDENTITY_VARIANT
    label: str = Field(min_length=1)
    full_name: str = Field(min_length=1)
    contact: VariantContactInput = Field(default_factory=VariantContactInput)
    links: list[VariantLinkInput] = Field(default_factory=list)
    is_default: bool = False


# The create/update body: the tool validates the payload against the member picked
# by ``kind``, so kind-specific required fields are enforced before any backend call.
ProfileWriteInput = Annotated[
    RoleWriteInput
    | ProjectWriteInput
    | CertificationWriteInput
    | EducationWriteInput
    | SkillWriteInput
    | IdentityVariantWriteInput,
    Field(discriminator="kind"),
]
