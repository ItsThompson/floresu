"""Rendering types: the registry-entry listing and the template-facing input view.

:class:`TemplateInfo` is what ``list_templates`` returns and the selector shows.
:class:`TemplateInputs` is the fully-mapped view of a resolved resume document the
pure input mapper produces; it is serialized to JSON and handed to Typst via
``sys.inputs`` (never as source), so it is the single contract the mapper and the
``.typ`` template agree on. Every field is required and present after mapping:
optionality was already resolved (absent contact fields and empty items dropped),
so the template never renders a placeholder.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TemplateInfo(BaseModel):
    """A template registry entry the selector lists."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str


class TemplateLink(BaseModel):
    """A labeled header link (portfolio, profile) rendered as selectable text."""

    model_config = ConfigDict(extra="forbid")

    label: str
    url: str


class TemplateSection(BaseModel):
    """One rendered section: its kind (drives bullet vs paragraph), title, and lines."""

    model_config = ConfigDict(extra="forbid")

    kind: str
    title: str
    items: list[str]


class TemplateInputs(BaseModel):
    """The template-facing projection of a resolved resume document."""

    model_config = ConfigDict(extra="forbid")

    full_name: str
    contact: list[str]
    links: list[TemplateLink]
    sections: list[TemplateSection]
