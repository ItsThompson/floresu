"""Unit tests for the resume document schema and its pure helpers.

Covers the boundary validators (id-keyed items must agree with their map key and
``item_order`` must be a permutation of them; section ids unique), the
discriminated item union, and the two pure helpers: the referenced-bullet set and
the fully resolved snapshot (references inlined as local items with provenance).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from floresu.resumes.document import (
    LibraryRefItem,
    LocalItem,
    ResumeDocument,
    ResumeSection,
    SectionKind,
    referenced_bullet_ids,
    resolve_document,
)


def _section(**overrides: object) -> ResumeSection:
    base: dict[str, object] = {
        "id": "sec-1",
        "kind": "work",
        "title": "Experience",
        "item_order": ["a", "b"],
        "items": {
            "a": {"id": "a", "kind": "library_ref", "bullet_id": 10},
            "b": {"id": "b", "kind": "local", "text": "Did a thing."},
        },
    }
    base.update(overrides)
    return ResumeSection.model_validate(base)


def test_a_valid_section_parses_its_discriminated_items() -> None:
    section = _section()
    assert isinstance(section.items["a"], LibraryRefItem)
    assert isinstance(section.items["b"], LocalItem)
    assert section.items["a"].bullet_id == 10


def test_item_map_key_must_equal_the_item_id() -> None:
    with pytest.raises(ValidationError):
        _section(items={"a": {"id": "MISMATCH", "kind": "local", "text": "x"}}, item_order=["a"])


def test_item_order_must_be_a_permutation_of_the_items() -> None:
    with pytest.raises(ValidationError):
        # 'b' is ordered but not present in the items map.
        _section(items={"a": {"id": "a", "kind": "local", "text": "x"}}, item_order=["a", "b"])


def test_item_order_rejects_duplicates() -> None:
    with pytest.raises(ValidationError):
        _section(
            items={"a": {"id": "a", "kind": "local", "text": "x"}},
            item_order=["a", "a"],
        )


def test_document_rejects_duplicate_section_ids() -> None:
    with pytest.raises(ValidationError):
        ResumeDocument(
            schema_version=1,
            template_id="default",
            sections=[
                ResumeSection(id="dup", kind=SectionKind.WORK, title="A"),
                ResumeSection(id="dup", kind=SectionKind.PROJECTS, title="B"),
            ],
        )


def test_an_empty_document_is_valid() -> None:
    document = ResumeDocument(schema_version=1, template_id="default")
    assert document.sections == []
    assert referenced_bullet_ids(document) == []


def test_referenced_bullet_ids_are_distinct_and_first_seen_ordered() -> None:
    document = ResumeDocument(
        schema_version=1,
        template_id="default",
        sections=[
            _section(
                id="s1",
                item_order=["a", "b", "c"],
                items={
                    "a": {"id": "a", "kind": "library_ref", "bullet_id": 20},
                    "b": {"id": "b", "kind": "library_ref", "bullet_id": 10},
                    "c": {"id": "c", "kind": "library_ref", "bullet_id": 20},
                },
            )
        ],
    )
    # First-seen order, de-duplicated (20 appears once, before 10).
    assert referenced_bullet_ids(document) == [20, 10]


def test_resolve_document_inlines_refs_as_local_items_with_provenance() -> None:
    document = ResumeDocument(schema_version=1, template_id="default", sections=[_section()])
    resolved = resolve_document(document, {10: "Cut latency 40%."})
    item = resolved.sections[0].items["a"]
    assert isinstance(item, LocalItem)
    assert item.text == "Cut latency 40%."
    assert item.forked_from_bullet_id == 10
    # The resolved document holds zero references, so a later library edit cannot
    # rewrite it.
    assert referenced_bullet_ids(resolved) == []
    # A local item is copied unchanged.
    copied = resolved.sections[0].items["b"]
    assert isinstance(copied, LocalItem)
    assert copied.text == "Did a thing."


def test_resolve_document_leaves_the_original_untouched() -> None:
    document = ResumeDocument(schema_version=1, template_id="default", sections=[_section()])
    resolve_document(document, {10: "resolved"})
    # The live document still references the canonical bullet.
    assert referenced_bullet_ids(document) == [10]
