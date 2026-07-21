"""Proof that the golden/hash-lock guard fails and passes in exactly the right cases.

The real schema is locked and must not change, so these tests drive the same pure
checks the release gate uses (:mod:`tests.resume_goldens`) with synthetic goldens,
locks, and schema models. They prove both directions the guard promises:

- an unversioned shape change is rejected (and a tampered golden or hash is caught);
- a properly versioned change (bump + new golden + upcaster) passes every check and
  the frozen old golden still upcasts to the current shape with its values intact.

This mirrors the way the upcaster is exercised with synthetic multi-step registries:
the machinery is real, the inputs are synthetic.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel, ConfigDict

from floresu.resumes.upcast import canonical_json, upcast_document
from tests.resume_goldens import (
    LockViolationError,
    ShapeDriftError,
    assert_current_shape_locked,
    assert_historical_goldens_upcast,
    assert_lock_matches,
    load_lock,
    sha256_hex,
)

if TYPE_CHECKING:
    from pathlib import Path


class _V1(BaseModel):
    """A synthetic v1 shape, standing in for a released document schema."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int
    template_id: str


class _V2(_V1):
    """The synthetic v2 shape: v1 plus a required ``summary`` a v1 doc lacks."""

    summary: str


def _v1_to_v2(document: dict[str, Any]) -> dict[str, Any]:
    """Backfill the field added in v2 so an old document round-trips to the new shape."""
    return {**document, "summary": "Seasoned engineer."}


def test_guard_rejects_a_shape_change_without_a_version_bump() -> None:
    committed = canonical_json({"schema_version": 1, "template_id": "classic"})
    # The shape gained a field but schema_version is still 1: this must fail.
    changed = canonical_json({"schema_version": 1, "template_id": "classic", "summary": ""})
    with pytest.raises(ShapeDriftError):
        assert_current_shape_locked(current=1, canonical_current=changed, goldens={1: committed})


def test_guard_rejects_a_missing_golden_for_the_current_version() -> None:
    with pytest.raises(ShapeDriftError):
        assert_current_shape_locked(current=2, canonical_current="{}", goldens={1: "{}"})


def test_guard_rejects_a_tampered_released_hash() -> None:
    golden = canonical_json({"schema_version": 1, "template_id": "classic"})
    with pytest.raises(LockViolationError):
        assert_lock_matches(goldens={1: golden}, lock={1: "0" * 64})


def test_guard_rejects_a_mutated_released_golden() -> None:
    original = canonical_json({"schema_version": 1, "template_id": "classic"})
    lock = {1: sha256_hex(original)}
    mutated = canonical_json({"schema_version": 1, "template_id": "tampered"})
    with pytest.raises(LockViolationError):
        assert_lock_matches(goldens={1: mutated}, lock=lock)


def test_guard_rejects_a_golden_with_no_lock_entry() -> None:
    golden = canonical_json({"schema_version": 1, "template_id": "classic"})
    with pytest.raises(LockViolationError):
        assert_lock_matches(goldens={1: golden}, lock={})


def test_guard_passes_on_a_properly_versioned_shape_change() -> None:
    # The v1 golden is frozen; the shape moved to v2 with a new golden and an
    # upcaster. Every gate check must now pass, and the old v1 golden must still
    # upcast to v2 with its real values intact.
    v1_text = canonical_json(_V1(schema_version=1, template_id="classic").model_dump(mode="json"))
    v2_text = canonical_json(
        _V2(schema_version=2, template_id="classic", summary="Seasoned engineer.").model_dump(
            mode="json"
        )
    )
    goldens = {1: v1_text, 2: v2_text}
    lock = {1: sha256_hex(v1_text), 2: sha256_hex(v2_text)}

    assert_current_shape_locked(current=2, canonical_current=v2_text, goldens=goldens)
    assert_lock_matches(goldens=goldens, lock=lock)

    def load(raw: Mapping[str, Any]) -> _V2:
        return _V2.model_validate(upcast_document(raw, upcasters={1: _v1_to_v2}, current=2))

    def invariants(document: _V2) -> None:
        assert document.schema_version == 2
        assert document.template_id == "classic"  # value carried through the upcast
        assert document.summary == "Seasoned engineer."

    assert_historical_goldens_upcast(goldens, load=load, invariants=invariants)


def test_backward_compat_fails_when_an_upcaster_drops_a_real_value() -> None:
    # A lossy upcaster that discards content must be caught: parsing succeeds but the
    # field value does not survive, so the invariants assertion fails.
    v1_text = canonical_json(_V1(schema_version=1, template_id="classic").model_dump(mode="json"))

    def lossy_v1_to_v2(document: dict[str, Any]) -> dict[str, Any]:
        return {**document, "template_id": "", "summary": "Seasoned engineer."}

    def load(raw: Mapping[str, Any]) -> _V2:
        return _V2.model_validate(upcast_document(raw, upcasters={1: lossy_v1_to_v2}, current=2))

    def invariants(document: _V2) -> None:
        assert document.template_id == "classic"

    with pytest.raises(AssertionError):
        assert_historical_goldens_upcast({1: v1_text}, load=load, invariants=invariants)


def test_load_lock_rejects_a_malformed_line(tmp_path: Path) -> None:
    path = tmp_path / "snapshots.lock"
    path.write_text("v1 not-a-real-sha256\n", encoding="utf-8")
    with pytest.raises(LockViolationError):
        load_lock(path)


def test_load_lock_rejects_a_duplicate_version(tmp_path: Path) -> None:
    sha = "a" * 64
    path = tmp_path / "snapshots.lock"
    path.write_text(f"v1 {sha}\nv1 {sha}\n", encoding="utf-8")
    with pytest.raises(LockViolationError):
        load_lock(path)


def test_load_lock_rejects_a_non_ascending_version(tmp_path: Path) -> None:
    sha = "a" * 64
    path = tmp_path / "snapshots.lock"
    path.write_text(f"v2 {sha}\nv1 {sha}\n", encoding="utf-8")
    with pytest.raises(LockViolationError):
        load_lock(path)


def test_load_lock_parses_comments_blank_lines_and_ascending_entries(tmp_path: Path) -> None:
    sha1, sha2 = "a" * 64, "b" * 64
    path = tmp_path / "snapshots.lock"
    path.write_text(f"# header comment\n\nv1 {sha1}\nv2 {sha2}\n", encoding="utf-8")
    assert load_lock(path) == {1: sha1, 2: sha2}
