"""The resume-schema release gate: golden drift, the hash lock, upcast, determinism.

These are the checks that gate release. They run in the normal backend suite (so a
local ``pytest`` catches drift at once) and again in the dedicated ``resume schema
lock`` CI job. The guard mechanism itself (that it fails on an unversioned shape
change and passes on a properly versioned one) is proved in
``test_resume_golden_guard.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from floresu.resumes.document import LibraryRefItem, LocalItem, ResumeDocument
from floresu.resumes.upcast import CURRENT_SCHEMA_VERSION, UPCASTERS, canonical_json, load_document
from tests.resume_goldens import (
    GOLDEN_BULLET_ID,
    GOLDEN_EMAIL,
    GOLDEN_FULL_NAME,
    GOLDEN_LOCAL_TEXT,
    GOLDEN_TEMPLATE_ID,
    GOLDEN_WORKLOG_IDS,
    assert_current_shape_locked,
    assert_historical_goldens_upcast,
    assert_lock_matches,
    build_golden_document,
    canonical_golden,
    load_goldens,
    load_lock,
)


def _load_to_current(raw: Mapping[str, Any]) -> ResumeDocument:
    """Upcast a stored golden to the current shape and validate it, as a read does."""
    return load_document(raw, upcasters=UPCASTERS, current=CURRENT_SCHEMA_VERSION)


def _assert_field_values_survive(document: ResumeDocument) -> None:
    """The real field values every golden must still carry after upcasting to current."""
    assert document.schema_version == CURRENT_SCHEMA_VERSION
    assert document.template_id == GOLDEN_TEMPLATE_ID
    snapshot = document.header.identity_snapshot
    assert snapshot is not None
    assert snapshot.full_name == GOLDEN_FULL_NAME
    assert snapshot.contact.email == GOLDEN_EMAIL
    work = next(section for section in document.sections if section.id == "sec-work")
    reference = work.items["item-ref"]
    assert isinstance(reference, LibraryRefItem)
    assert reference.bullet_id == GOLDEN_BULLET_ID
    fork = work.items["item-fork"]
    assert isinstance(fork, LocalItem)
    assert fork.text == GOLDEN_LOCAL_TEXT
    assert fork.forked_from_bullet_id == GOLDEN_BULLET_ID
    assert fork.source_refs is not None
    assert fork.source_refs.worklog_ids == GOLDEN_WORKLOG_IDS


def test_a_committed_golden_exists_for_the_current_version() -> None:
    assert CURRENT_SCHEMA_VERSION in load_goldens()


def test_current_document_shape_matches_the_committed_golden() -> None:
    # A change to the document shape without a schema_version bump changes this
    # canonical form and fails here: the drift guard.
    assert_current_shape_locked(
        current=CURRENT_SCHEMA_VERSION,
        canonical_current=canonical_golden(build_golden_document(CURRENT_SCHEMA_VERSION)),
        goldens=load_goldens(),
    )


def test_snapshots_lock_matches_every_committed_golden() -> None:
    # Editing a released golden or its recorded sha256 breaks this hash check.
    assert_lock_matches(goldens=load_goldens(), lock=load_lock())


def test_every_historical_golden_upcasts_to_current_and_preserves_field_values() -> None:
    assert_historical_goldens_upcast(
        load_goldens(),
        load=_load_to_current,
        invariants=_assert_field_values_survive,
    )


def _reverse_key_order(value: Any) -> Any:
    """Rebuild every nested map with reversed key insertion order; arrays untouched."""
    if isinstance(value, dict):
        return {key: _reverse_key_order(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [_reverse_key_order(element) for element in value]
    return value


def test_canonical_serialization_is_byte_stable_across_runs() -> None:
    payload = build_golden_document(CURRENT_SCHEMA_VERSION).model_dump(mode="json")
    first = canonical_json(payload)
    # Repeated serialization of the same payload is byte-identical.
    assert [canonical_json(payload) for _ in range(5)] == [first] * 5
    # Nested-map key insertion order does not affect the bytes (stable key order).
    assert canonical_json(_reverse_key_order(payload)) == first
