"""Unit tests for the default opaque-id factory.

``new_hex_id`` is the single ``IdFactory`` default injected across the domain
seams. It must hand back a fresh uuid4 hex string so a deterministic id sequence
is a drop-in for it in tests.
"""

from __future__ import annotations

from uuid import UUID

from floresu.core.ids import new_hex_id


def test_new_hex_id_is_a_uuid4_hex_string() -> None:
    value = new_hex_id()
    assert len(value) == 32
    # A uuid4 hex round-trips through UUID and reports version 4.
    assert UUID(hex=value).version == 4


def test_new_hex_id_is_unique_per_call() -> None:
    assert new_hex_id() != new_hex_id()
