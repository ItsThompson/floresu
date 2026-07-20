"""Unit tests for the concurrency-safe tag get-or-create in the SQLAlchemy repo.

Worklog is written by both the human web app and the agent, so two concurrent
writes can introduce the same new tag label for one user and race on the initial
SELECT. These tests substitute the ``AsyncSession`` boundary to simulate the
unique-constraint breach deterministically (a real race is timing-dependent): the
first tag SELECT misses, the nested INSERT breaches ``uq_tags_user_id``, and the
repository refetches the row the concurrent writer committed instead of 500ing.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from floresu.worklog.models import Tag
from floresu.worklog.repository import SqlAlchemyWorklogRepository


class _UniqueOrigError(Exception):
    """A stand-in DBAPI error carrying the Postgres unique-violation SQLSTATE."""

    def __init__(self, sqlstate: str) -> None:
        self.sqlstate = sqlstate
        super().__init__(sqlstate)


class _Result:
    def __init__(self, value: Tag | None) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Tag | None:
        return self._value


class _Savepoint:
    """A begin_nested() stand-in that re-raises the flush error like a real savepoint."""

    async def __aenter__(self) -> _Savepoint:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False


class _RaceSession:
    """Simulates the concurrent-insert race at the session boundary.

    The first ``execute`` (the initial find) misses; ``flush`` inside the savepoint
    raises an ``IntegrityError`` with the given SQLSTATE; a later ``execute`` (the
    refetch) returns the row a concurrent writer committed.
    """

    def __init__(self, refetched: Tag, *, sqlstate: str) -> None:
        self._refetched = refetched
        self._sqlstate = sqlstate
        self._selects = 0

    async def execute(self, _statement: Any) -> _Result:
        self._selects += 1
        return _Result(None if self._selects == 1 else self._refetched)

    def add(self, _obj: object) -> None:
        pass

    async def flush(self) -> None:
        raise IntegrityError("INSERT", {}, orig=_UniqueOrigError(self._sqlstate))

    def begin_nested(self) -> _Savepoint:
        return _Savepoint()


def _repo(session: _RaceSession) -> SqlAlchemyWorklogRepository:
    return SqlAlchemyWorklogRepository(cast(AsyncSession, session))


async def test_get_or_create_tag_refetches_on_a_concurrent_unique_violation() -> None:
    existing = Tag(user_id=1, label="api")
    existing.id = 7
    tag = await _repo(_RaceSession(existing, sqlstate="23505")).get_or_create_tag(1, "api")
    # The racing insert breached the unique constraint; the row is reused, not a 500.
    assert tag is existing


async def test_get_or_create_tag_reraises_a_non_unique_integrity_error() -> None:
    existing = Tag(user_id=1, label="api")
    existing.id = 7
    with pytest.raises(IntegrityError):
        # A non-unique breach (e.g. a foreign-key violation) is not swallowed.
        await _repo(_RaceSession(existing, sqlstate="23503")).get_or_create_tag(1, "api")
