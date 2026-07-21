"""Unit tests for the shared unique-violation → Conflict mapper.

Services wrap their writes in ``conflict_on_duplicate`` so a ``UNIQUE`` breach
becomes a recoverable :class:`Conflict`. These tests exercise the helper directly:
a unique-violation ``IntegrityError`` is mapped to a Conflict, and a non-unique
integrity error propagates unchanged.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from floresu.core.conflicts import conflict_on_duplicate
from floresu.core.errors import Conflict


class _OrigError(Exception):
    def __init__(self, sqlstate: str) -> None:
        self.sqlstate = sqlstate
        super().__init__(sqlstate)


async def test_unique_violation_becomes_a_conflict() -> None:
    with pytest.raises(Conflict) as excinfo:
        async with conflict_on_duplicate("already exists"):
            raise IntegrityError("INSERT", {}, orig=_OrigError("23505"))
    assert "already exists" in excinfo.value.detail


async def test_a_non_unique_integrity_error_propagates() -> None:
    # A foreign-key violation (23503) is not a duplicate; it must not be swallowed.
    with pytest.raises(IntegrityError):
        async with conflict_on_duplicate("already exists"):
            raise IntegrityError("INSERT", {}, orig=_OrigError("23503"))


async def test_a_clean_block_yields_without_error() -> None:
    entered = False
    async with conflict_on_duplicate("already exists"):
        entered = True
    assert entered
