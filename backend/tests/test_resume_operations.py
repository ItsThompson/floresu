"""Unit tests for the pure resume operations: document surgery and write guards.

These functions carry no persistence and no I/O, so each is exercised directly:
build an add-item projection, locate a section or item, fork or promote an item in
an in-memory document, permute an order, re-run the document validators after a
mutation, guard the write preconditions, and build the audit summary lines. The
document builders below mirror the boundary shapes ``test_resume_document.py`` uses.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from floresu.core.errors import Conflict, NotFound, Validation
from floresu.resumes.document import (
    LibraryRefItem,
    LocalItem,
    LocalItemSourceRefs,
    ResumeDocument,
    ResumeSection,
)
from floresu.resumes.models import Resume, ResumeKind, ResumeStatus
from floresu.resumes.operations import (
    application_submitted_summary,
    apply_item_order,
    apply_section_order,
    build_item,
    bullet_forked_summary,
    created_summary,
    edited_summary,
    finalized_summary,
    find_item_section,
    find_local_item,
    find_section,
    fork_bullet_reference,
    guard_editable,
    guard_finalizable,
    guard_revision,
    item_added_summary,
    item_removed_summary,
    promoted_summary,
    reordered_summary,
    resume_not_found,
    revalidate_document,
    swap_item_to_reference,
)
from floresu.resumes.schemas import LibraryRefItemInput, LocalItemInput


def _ref(item_id: str, bullet_id: int) -> dict[str, object]:
    return {"id": item_id, "kind": "library_ref", "bullet_id": bullet_id}


def _local(item_id: str, text: str) -> dict[str, object]:
    return {"id": item_id, "kind": "local", "text": text}


def _section(
    section_id: str, item_order: list[str], items: dict[str, dict[str, object]]
) -> dict[str, object]:
    return {
        "id": section_id,
        "kind": "work",
        "title": "Experience",
        "item_order": item_order,
        "items": items,
    }


def _document(sections: list[dict[str, object]]) -> ResumeDocument:
    return ResumeDocument.model_validate(
        {"schema_version": 1, "template_id": "default", "sections": sections}
    )


def _resume(
    *,
    kind: ResumeKind = ResumeKind.LIVING,
    status: ResumeStatus = ResumeStatus.DRAFT,
    revision: int = 1,
    title: str = "CV",
) -> Resume:
    return Resume(
        id=1,
        user_id=1,
        kind=kind,
        status=status,
        title=title,
        schema_version=1,
        revision=revision,
        document={},
    )


# --- build_item --------------------------------------------------------------


def test_build_item_projects_a_library_ref_input_stamping_the_id() -> None:
    item = build_item(LibraryRefItemInput(bullet_id=10), "item-1")
    assert isinstance(item, LibraryRefItem)
    assert item.id == "item-1"
    assert item.bullet_id == 10


def test_build_item_projects_a_local_input_carrying_its_source_refs() -> None:
    refs = LocalItemSourceRefs(source_ids=[3], worklog_ids=[4])
    item = build_item(LocalItemInput(text="Shipped the thing.", source_refs=refs), "item-2")
    assert isinstance(item, LocalItem)
    assert item.id == "item-2"
    assert item.text == "Shipped the thing."
    assert item.source_refs == refs


# --- find_section / find_item_section ----------------------------------------


def test_find_section_returns_the_section_with_that_id() -> None:
    document = _document([_section("sec-1", [], {}), _section("sec-2", [], {})])
    assert find_section(document, "sec-2").id == "sec-2"


def test_find_section_rejects_an_unknown_id() -> None:
    document = _document([_section("sec-1", [], {})])
    with pytest.raises(Validation):
        find_section(document, "nope")


def test_find_item_section_returns_the_section_holding_the_item() -> None:
    document = _document(
        [
            _section("sec-1", ["a"], {"a": _local("a", "one")}),
            _section("sec-2", ["b"], {"b": _local("b", "two")}),
        ]
    )
    assert find_item_section(document, "b").id == "sec-2"


def test_find_item_section_raises_not_found_when_no_section_holds_it() -> None:
    document = _document([_section("sec-1", ["a"], {"a": _local("a", "one")})])
    with pytest.raises(NotFound):
        find_item_section(document, "ghost")


# --- fork_bullet_reference ---------------------------------------------------


def test_fork_bullet_reference_forks_every_matching_ref_across_sections() -> None:
    document = _document(
        [
            _section("s1", ["a"], {"a": _ref("a", 10)}),
            _section("s2", ["b", "c"], {"b": _ref("b", 10), "c": _ref("c", 20)}),
        ]
    )
    forked = fork_bullet_reference(document, 10, "Edited only here.")
    assert forked == 2
    first = document.sections[0].items["a"]
    second = document.sections[1].items["b"]
    other = document.sections[1].items["c"]
    assert isinstance(first, LocalItem)
    assert first.id == "a"
    assert first.text == "Edited only here."
    assert first.forked_from_bullet_id == 10
    assert isinstance(second, LocalItem)
    assert second.forked_from_bullet_id == 10
    # A reference to a different bullet is left untouched.
    assert isinstance(other, LibraryRefItem)
    assert other.bullet_id == 20


def test_fork_bullet_reference_rejects_a_bullet_the_resume_does_not_reference() -> None:
    document = _document([_section("s1", ["a"], {"a": _local("a", "inline")})])
    with pytest.raises(Validation):
        fork_bullet_reference(document, 10, "text")


# --- find_local_item / swap_item_to_reference --------------------------------


def test_find_local_item_returns_a_resume_local_item() -> None:
    document = _document([_section("s1", ["a"], {"a": _local("a", "inline")})])
    item = find_local_item(document, "a")
    assert isinstance(item, LocalItem)
    assert item.text == "inline"


def test_find_local_item_rejects_a_library_reference() -> None:
    document = _document([_section("s1", ["a"], {"a": _ref("a", 10)})])
    with pytest.raises(Validation):
        find_local_item(document, "a")


def test_find_local_item_raises_not_found_when_the_item_is_missing() -> None:
    document = _document([_section("s1", [], {})])
    with pytest.raises(NotFound):
        find_local_item(document, "ghost")


def test_swap_item_to_reference_replaces_a_local_item_keeping_its_id() -> None:
    document = _document([_section("s1", ["a"], {"a": _local("a", "inline")})])
    swap_item_to_reference(document, "a", 42)
    item = document.sections[0].items["a"]
    assert isinstance(item, LibraryRefItem)
    assert item.id == "a"
    assert item.bullet_id == 42


# --- apply_section_order / apply_item_order ----------------------------------


def test_apply_section_order_permutes_the_sections() -> None:
    document = _document([_section("s1", [], {}), _section("s2", [], {}), _section("s3", [], {})])
    apply_section_order(document, ["s3", "s1", "s2"])
    assert [section.id for section in document.sections] == ["s3", "s1", "s2"]


def test_apply_section_order_rejects_duplicate_ids() -> None:
    document = _document([_section("s1", [], {}), _section("s2", [], {})])
    with pytest.raises(Validation):
        apply_section_order(document, ["s1", "s1"])


def test_apply_section_order_rejects_a_partial_permutation() -> None:
    document = _document([_section("s1", [], {}), _section("s2", [], {})])
    with pytest.raises(Validation):
        apply_section_order(document, ["s1"])


def _two_item_section() -> ResumeSection:
    document = _document(
        [_section("s1", ["a", "b"], {"a": _local("a", "x"), "b": _local("b", "y")})]
    )
    return document.sections[0]


def test_apply_item_order_permutes_a_sections_items() -> None:
    section = _two_item_section()
    apply_item_order(section, ["b", "a"])
    assert section.item_order == ["b", "a"]


def test_apply_item_order_rejects_duplicate_ids() -> None:
    section = _two_item_section()
    with pytest.raises(Validation):
        apply_item_order(section, ["a", "a"])


def test_apply_item_order_rejects_a_partial_permutation() -> None:
    section = _two_item_section()
    with pytest.raises(Validation):
        apply_item_order(section, ["a"])


# --- revalidate_document -----------------------------------------------------


def test_revalidate_document_returns_a_validated_copy_reflecting_a_mutation() -> None:
    document = _document([_section("s1", ["a"], {"a": _local("a", "inline")})])
    swap_item_to_reference(document, "a", 42)
    revalidated = revalidate_document(document)
    item = revalidated.sections[0].items["a"]
    assert isinstance(item, LibraryRefItem)
    assert item.bullet_id == 42


def test_revalidate_document_rejects_a_document_whose_invariant_was_broken() -> None:
    document = _document([_section("s1", ["a"], {"a": _local("a", "inline")})])
    # Force a broken invariant: a map key that disagrees with its item id.
    document.sections[0].items["b"] = LocalItem(id="mismatch", text="x")
    with pytest.raises(ValidationError):
        revalidate_document(document)


# --- write guards ------------------------------------------------------------


def test_guard_editable_allows_a_draft() -> None:
    guard_editable(_resume(status=ResumeStatus.DRAFT))


def test_guard_editable_rejects_a_finalized_resume() -> None:
    with pytest.raises(Conflict):
        guard_editable(_resume(status=ResumeStatus.FINALIZED))


def test_guard_finalizable_allows_an_application_draft() -> None:
    guard_finalizable(_resume(kind=ResumeKind.APPLICATION, status=ResumeStatus.DRAFT))


def test_guard_finalizable_rejects_a_living_resume() -> None:
    with pytest.raises(Conflict):
        guard_finalizable(_resume(kind=ResumeKind.LIVING))


def test_guard_finalizable_rejects_an_already_finalized_resume() -> None:
    with pytest.raises(Conflict):
        guard_finalizable(_resume(kind=ResumeKind.APPLICATION, status=ResumeStatus.FINALIZED))


def test_guard_revision_allows_a_matching_if_match() -> None:
    guard_revision(_resume(revision=3), 3)


def test_guard_revision_rejects_a_stale_if_match() -> None:
    with pytest.raises(Conflict):
        guard_revision(_resume(revision=4), 3)


# --- not-found factory and summary lines -------------------------------------


def test_resume_not_found_carries_the_id() -> None:
    error = resume_not_found(77)
    assert isinstance(error, NotFound)
    assert "77" in str(error)


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        (created_summary, "Created living resume “CV”"),
        (edited_summary, "Edited resume “CV”"),
        (item_added_summary, "Added an item to resume “CV”"),
        (item_removed_summary, "Removed an item from resume “CV”"),
        (reordered_summary, "Reordered resume “CV”"),
        (bullet_forked_summary, "Edited a bullet only on resume “CV”"),
        (promoted_summary, "Promoted an item from resume “CV” into the library"),
        (finalized_summary, "Finalized resume “CV”"),
        (
            application_submitted_summary,
            "Marked the application submitted by finalizing resume “CV”",
        ),
    ],
)
def test_summary_lines_name_the_resume(summary: Callable[[Resume], str], expected: str) -> None:
    assert summary(_resume()) == expected
