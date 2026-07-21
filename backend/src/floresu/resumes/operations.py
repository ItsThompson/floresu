"""Pure operations the resume service orchestrates: document surgery and guards.

These functions carry no persistence and no I/O: they validate the creation
contract, apply an edit to an in-memory :class:`ResumeDocument` (add an item, find
a section, permute an order), re-run the document validators after a mutation,
guard the write preconditions (a finalized resume is read-only; a stale revision
is a recoverable conflict), and build the audit summary lines. The service depends
on them so its methods stay a thin sequence of load, guard, mutate, and save.
"""

from __future__ import annotations

from floresu.core.errors import Conflict, NotFound, Unauthorized, Validation
from floresu.resumes.document import (
    LibraryRefItem,
    LocalItem,
    ResumeDocument,
    ResumeSection,
)
from floresu.resumes.models import Resume, ResumeStatus
from floresu.resumes.schemas import LibraryRefItemInput, ResumeItemInput


def build_item(item_input: ResumeItemInput, item_id: str) -> LibraryRefItem | LocalItem:
    """Project an add-item input onto a document item, stamping the server-minted id."""
    if isinstance(item_input, LibraryRefItemInput):
        return LibraryRefItem(id=item_id, bullet_id=item_input.bullet_id)
    return LocalItem(id=item_id, text=item_input.text, source_refs=item_input.source_refs)


def find_section(document: ResumeDocument, section_id: str) -> ResumeSection:
    """The section with ``section_id``, or a validation error if there is none."""
    for section in document.sections:
        if section.id == section_id:
            return section
    raise Validation(
        "No section with that id on this resume.",
        fields={"section_id": f"Unknown section id {section_id!r}."},
    )


def find_item_section(document: ResumeDocument, item_id: str) -> ResumeSection:
    """The section holding ``item_id``, or a not-found error if no section holds it."""
    for section in document.sections:
        if item_id in section.items:
            return section
    raise NotFound(f"No item with id {item_id!r} on this resume.")


def apply_section_order(document: ResumeDocument, order: list[str]) -> None:
    """Permute the sections to ``order`` (a full, non-colliding permutation of section ids)."""
    current = {section.id: section for section in document.sections}
    if len(set(order)) != len(order):
        raise Validation("The section order contains duplicate ids.")
    if set(order) != set(current):
        raise Validation(
            "A section reorder must list every section exactly once.",
            fields={"section_order": f"Expected the {len(current)} section id(s)."},
        )
    document.sections = [current[section_id] for section_id in order]


def apply_item_order(section: ResumeSection, order: list[str]) -> None:
    """Permute a section's items to ``order`` (a full, non-colliding permutation of item ids)."""
    if len(set(order)) != len(order):
        raise Validation("An item order contains duplicate ids.")
    if set(order) != set(section.items):
        raise Validation(
            "An item reorder must list every item in the section exactly once.",
            fields={"item_order": f"Expected the {len(section.items)} item id(s)."},
        )
    section.item_order = list(order)


def revalidate_document(document: ResumeDocument) -> ResumeDocument:
    """Re-run the document validators after an in-place mutation."""
    return ResumeDocument.model_validate(document.model_dump(mode="python"))


def guard_editable(resume: Resume) -> None:
    """A finalized resume is read-only; the only path is to fork a new draft copy."""
    if resume.status is ResumeStatus.FINALIZED:
        raise Conflict("This resume is finalized and read-only; fork a new draft copy to edit.")


def guard_revision(resume: Resume, if_match: int) -> None:
    """Reject a stale write with a recoverable re-read/retry conflict."""
    if resume.revision != if_match:
        raise Conflict(
            "This resume changed since you loaded it "
            f"(you sent revision {if_match}, current is {resume.revision}); re-read and retry."
        )


def require_user_pk(user_id: str) -> int:
    """Cast the resolved string identity to the bigint PK, or reject as stale."""
    try:
        return int(user_id)
    except ValueError as exc:
        raise Unauthorized("Session is invalid or expired.") from exc


def resume_not_found(resume_id: int) -> NotFound:
    # 404-over-403: a resume another account owns is scoped out of the read, so a
    # miss is indistinguishable from "does not exist" (no existence leak).
    return NotFound(f"No resume with id {resume_id}.")


def created_summary(resume: Resume) -> str:
    return f"Created {resume.kind.value} resume “{resume.title}”"


def edited_summary(resume: Resume) -> str:
    return f"Edited resume “{resume.title}”"


def item_added_summary(resume: Resume) -> str:
    return f"Added an item to resume “{resume.title}”"


def item_removed_summary(resume: Resume) -> str:
    return f"Removed an item from resume “{resume.title}”"


def reordered_summary(resume: Resume) -> str:
    return f"Reordered resume “{resume.title}”"
