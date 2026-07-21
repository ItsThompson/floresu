"""The pure input mapper: a resolved resume document to template inputs.

This is the only place that knows both the resume document shape and the template's
input contract, and it is pure and I/O-free, so it is exhaustively unit-tested:
given a resolved document it returns the template-facing view. It assumes the
document is already resolved: every item inlined as a :class:`LocalItem` (references
resolved to text) and the header carrying an :class:`IdentitySnapshot`. The resume
render service performs that resolution before calling render; a stray unresolved
reference is skipped rather than rendered as a blank line.

Optionality is resolved here, not in the template: absent contact fields and empty
sections/items are dropped, so the template never emits placeholder text.
"""

from __future__ import annotations

from floresu.rendering.schemas import TemplateInputs, TemplateLink, TemplateSection
from floresu.resumes.document import (
    IdentitySnapshot,
    LibraryRefItem,
    LocalItem,
    ResumeDocument,
    ResumeSection,
)


def _contact_lines(snapshot: IdentitySnapshot) -> list[str]:
    """The present contact fields in a stable display order; absent fields omitted."""
    candidates = [snapshot.contact.email, snapshot.contact.phone, snapshot.contact.location]
    return [value for value in candidates if value]


def _section_lines(section: ResumeSection) -> list[str]:
    """The section's item texts in order; a resolved doc holds only inline text."""
    lines: list[str] = []
    for item_id in section.item_order:
        item: LibraryRefItem | LocalItem = section.items[item_id]
        if isinstance(item, LocalItem):
            lines.append(item.text)
    return lines


def to_template_inputs(document: ResumeDocument) -> TemplateInputs:
    """Project a resolved resume document onto the template-facing input view."""
    snapshot = document.header.identity_snapshot
    full_name = snapshot.full_name if snapshot is not None else ""
    contact = _contact_lines(snapshot) if snapshot is not None else []
    links = (
        [TemplateLink(label=link.label, url=link.url) for link in snapshot.links]
        if snapshot is not None
        else []
    )
    sections = [
        TemplateSection(kind=section.kind.value, title=section.title, items=_section_lines(section))
        for section in document.sections
    ]
    return TemplateInputs(full_name=full_name, contact=contact, links=links, sections=sections)
