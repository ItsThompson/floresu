"""The pure input mapper: resolved resume document to template inputs.

The mapper is the high-value pure target (it is the only place that knows both the
document shape and the template contract), so it is tested exhaustively: header
projection, present-only contact ordering, links, section kind/title/items in order,
and the resolved-only guarantee (a stray unresolved reference is dropped, never
rendered as a blank line).
"""

from __future__ import annotations

from floresu.rendering.mapper import to_template_inputs
from floresu.resumes.document import (
    IdentitySnapshot,
    IdentitySnapshotContact,
    LibraryRefItem,
    LocalItem,
    ResumeDocument,
    ResumeHeader,
    ResumeSection,
    SectionKind,
)
from tests.rendering_fakes import build_resolved_document, build_snapshot, local_section


def test_header_projects_name_present_contact_lines_and_links() -> None:
    inputs = to_template_inputs(build_resolved_document(sections=[]))

    assert inputs.full_name == "Ada Lovelace"
    assert inputs.contact == ["ada@example.com", "+1 555 0100", "London, UK"]
    assert [link.model_dump() for link in inputs.links] == [
        {"label": "portfolio", "url": "https://ada.example.com"}
    ]


def test_absent_contact_fields_are_omitted_in_display_order() -> None:
    snapshot = IdentitySnapshot(
        full_name="Grace Hopper",
        contact=IdentitySnapshotContact(location="Arlington, VA"),
    )
    inputs = to_template_inputs(build_resolved_document(snapshot=snapshot, sections=[]))

    # Only the present field, and no placeholder for the missing email/phone.
    assert inputs.contact == ["Arlington, VA"]
    assert inputs.links == []


def test_a_document_without_a_snapshot_maps_to_an_empty_header() -> None:
    document = ResumeDocument(
        schema_version=1,
        header=ResumeHeader(identity_variant_id=5),
        template_id="classic",
        sections=[],
    )
    inputs = to_template_inputs(document)

    assert inputs.full_name == ""
    assert inputs.contact == []
    assert inputs.links == []


def test_sections_map_kind_title_and_items_in_order() -> None:
    sections = [
        local_section("s1", "summary", "Summary", ["A one-line summary."]),
        local_section("s2", "work", "Experience", ["Shipped X.", "Owned Y."]),
    ]
    inputs = to_template_inputs(build_resolved_document(sections=sections))

    assert [(section.kind, section.title, section.items) for section in inputs.sections] == [
        ("summary", "Summary", ["A one-line summary."]),
        ("work", "Experience", ["Shipped X.", "Owned Y."]),
    ]


def test_items_follow_item_order_not_map_insertion_order() -> None:
    section = ResumeSection(
        id="s",
        kind=SectionKind.WORK,
        title="Experience",
        item_order=["b", "a"],
        items={
            "a": LocalItem(id="a", text="second"),
            "b": LocalItem(id="b", text="first"),
        },
    )
    inputs = to_template_inputs(build_resolved_document(sections=[section]))

    assert inputs.sections[0].items == ["first", "second"]


def test_an_unresolved_reference_is_dropped_rather_than_rendered_blank() -> None:
    # A resolved document should hold only local items; a stray library_ref (a
    # resolution bug) must not surface as an empty bullet line.
    section = ResumeSection(
        id="s",
        kind=SectionKind.WORK,
        title="Experience",
        item_order=["ref", "local"],
        items={
            "ref": LibraryRefItem(id="ref", bullet_id=99),
            "local": LocalItem(id="local", text="kept"),
        },
    )
    inputs = to_template_inputs(build_resolved_document(sections=[section]))

    assert inputs.sections[0].items == ["kept"]


def test_snapshot_helper_round_trips_through_the_mapper() -> None:
    inputs = to_template_inputs(build_resolved_document(snapshot=build_snapshot(full_name="X Y")))
    assert inputs.full_name == "X Y"
