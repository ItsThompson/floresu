"""Wire schemas for identity variants: the write body and the read shape.

A write (:class:`IdentityVariantWrite`) carries the label, display name, the
optional contact fields, the links, and ``is_default``. The same shape backs
create and full-representation update: setting ``is_default`` true is how a variant
is promoted to default (the service flips the previous one off). IDs, timestamps,
and ``archived_at`` are server-owned and never accepted on a write.

Contact and links are stored as JSONB. :class:`VariantContact` keeps every contact
field optional (a variant may omit email, phone, or location), and the contact is
stored with unset fields dropped so the JSONB stays tidy; a read reconstructs the
absent fields as ``None``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from floresu.profile.variants.models import IdentityVariant


class VariantContact(BaseModel):
    """A variant's contact fields; each is optional (a variant may omit any)."""

    model_config = ConfigDict(extra="forbid")

    email: str | None = None
    phone: str | None = None
    location: str | None = None


class VariantLink(BaseModel):
    """A labeled link (e.g. a portfolio or profile URL)."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    url: str = Field(min_length=1)


class IdentityVariantWrite(BaseModel):
    """The create/update body: label, name, optional contact, links, default flag."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    full_name: str = Field(min_length=1)
    contact: VariantContact = Field(default_factory=VariantContact)
    links: list[VariantLink] = Field(default_factory=list)
    is_default: bool = False


class IdentityVariantRead(BaseModel):
    """A variant with its default flag and archive state."""

    model_config = ConfigDict(extra="forbid")

    id: int
    label: str
    full_name: str
    contact: VariantContact
    links: list[VariantLink]
    is_default: bool
    archived_at: datetime | None


def contact_to_storage(contact: VariantContact) -> dict[str, str]:
    """Project the contact onto its JSONB form, dropping unset (``None``) fields."""
    return contact.model_dump(exclude_none=True)


def links_to_storage(links: list[VariantLink]) -> list[dict[str, str]]:
    """Project the links onto their JSONB form."""
    return [link.model_dump() for link in links]


def to_read(variant: IdentityVariant) -> IdentityVariantRead:
    """Project an ``identity_variants`` ORM row onto the read shape."""
    return IdentityVariantRead(
        id=variant.id,
        label=variant.label,
        full_name=variant.full_name,
        contact=VariantContact.model_validate(variant.contact),
        links=[VariantLink.model_validate(link) for link in variant.links],
        is_default=variant.is_default,
        archived_at=variant.archived_at,
    )
