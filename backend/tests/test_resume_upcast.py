"""Unit tests for schema versioning: the read-time upcaster and canonical form.

Exercises the upcaster chain with synthetic multi-step registries (the real
registry is empty at v1), the guards (a document newer than current is rejected, a
gap in the chain is a hard error, a missing/invalid version is a validation error),
and the byte-stable canonical serialization (stable key ordering for nested maps,
preserved array order).
"""

from __future__ import annotations

from typing import Any

import pytest

from floresu.core.errors import Validation
from floresu.resumes.upcast import canonical_json, load_document, upcast_document


def test_a_current_document_passes_through_unchanged() -> None:
    raw = {"schema_version": 1, "template_id": "default", "sections": []}
    assert upcast_document(raw)["schema_version"] == 1


def test_the_upcaster_chain_runs_every_step_to_current() -> None:
    def v1_to_v2(doc: dict[str, Any]) -> dict[str, Any]:
        return {**doc, "added_in_v2": True}

    def v2_to_v3(doc: dict[str, Any]) -> dict[str, Any]:
        return {**doc, "added_in_v3": True}

    raw = {"schema_version": 1, "template_id": "default", "sections": []}
    result = upcast_document(raw, upcasters={1: v1_to_v2, 2: v2_to_v3}, current=3)
    assert result["schema_version"] == 3
    assert result["added_in_v2"] is True
    assert result["added_in_v3"] is True


def test_a_document_newer_than_current_is_rejected() -> None:
    raw = {"schema_version": 5, "template_id": "default", "sections": []}
    with pytest.raises(Validation):
        upcast_document(raw, current=1)


def test_a_gap_in_the_chain_is_a_hard_error() -> None:
    raw = {"schema_version": 1, "template_id": "default", "sections": []}
    # No registered step for v1, but current is 3: a half-migrated document must
    # never be served.
    with pytest.raises(RuntimeError):
        upcast_document(raw, upcasters={}, current=3)


def test_a_missing_or_non_integer_version_is_a_validation_error() -> None:
    with pytest.raises(Validation):
        upcast_document({"template_id": "default", "sections": []})
    with pytest.raises(Validation):
        upcast_document({"schema_version": "1", "template_id": "default", "sections": []})
    # A bool is not an acceptable version even though it is an int subclass.
    with pytest.raises(Validation):
        upcast_document({"schema_version": True, "template_id": "default", "sections": []})


def test_load_document_upcasts_then_validates() -> None:
    def v1_to_v2(doc: dict[str, Any]) -> dict[str, Any]:
        return doc

    raw = {"schema_version": 1, "template_id": "default", "sections": []}
    document = load_document(raw, upcasters={1: v1_to_v2}, current=2)
    assert document.schema_version == 2


def test_canonical_json_is_byte_stable_regardless_of_key_order() -> None:
    a = {"schema_version": 1, "template_id": "default", "header": {"identity_variant_id": 3}}
    b = {"header": {"identity_variant_id": 3}, "template_id": "default", "schema_version": 1}
    assert canonical_json(a) == canonical_json(b)


def test_canonical_json_preserves_array_order() -> None:
    # Object keys sort; array order is meaningful and must be preserved.
    forward = canonical_json({"item_order": ["b", "a", "c"]})
    assert forward == '{"item_order":["b","a","c"]}'
