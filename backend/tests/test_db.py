"""DB layer unit tests: the pieces that need no live Postgres.

The transaction commit/rollback boundary is additionally verified against a real
Postgres in ``test_db_integration.py``; here a spy session covers its control flow
so a Docker-less checkout still exercises it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from floresu.core.db import (
    Database,
    create_database,
    create_db_engine,
    create_db_lifespan,
    create_sessionmaker,
    db_readiness_check,
    get_session,
    group_pairs_into_dict,
    is_unique_violation,
    owned_ids,
    transaction,
)
from floresu.core.post_commit import enqueue_post_commit
from floresu.profile.models import Source

_DSN = "postgresql+asyncpg://floresu:floresu@localhost:5432/floresu"


class _SpySession:
    """Records commit/rollback so the transaction boundary is verifiable offline.

    Carries an ``info`` dict like a real session, so the transaction boundary's
    post-commit queue drain/discard (:mod:`floresu.core.post_commit`) has somewhere
    to read from.
    """

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.info: dict[str, object] = {}

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


async def test_transaction_commits_on_a_clean_exit() -> None:
    session = _SpySession()
    async with transaction(session):  # type: ignore[arg-type]
        pass
    assert session.committed is True
    assert session.rolled_back is False


async def test_transaction_rolls_back_and_reraises_on_error() -> None:
    session = _SpySession()
    with pytest.raises(ValueError, match="boom"):
        async with transaction(session):  # type: ignore[arg-type]
            raise ValueError("boom")
    assert session.rolled_back is True
    assert session.committed is False


async def test_transaction_runs_queued_post_commit_tasks_after_a_clean_commit() -> None:
    session = _SpySession()
    ran: list[str] = []

    async def task() -> None:
        ran.append("ran")

    async with transaction(session):  # type: ignore[arg-type]
        enqueue_post_commit(session, task)  # type: ignore[arg-type]
        assert ran == []  # deferred: not run inside the block
    assert session.committed is True
    assert ran == ["ran"]  # run once the commit succeeded


async def test_transaction_discards_post_commit_tasks_on_rollback() -> None:
    session = _SpySession()
    ran: list[str] = []

    async def task() -> None:
        ran.append("ran")

    with pytest.raises(ValueError, match="boom"):
        async with transaction(session):  # type: ignore[arg-type]
            enqueue_post_commit(session, task)  # type: ignore[arg-type]
            raise ValueError("boom")
    assert session.rolled_back is True
    assert ran == []  # a rolled-back write never runs its side channels


def test_is_unique_violation_matches_only_the_unique_sqlstate() -> None:
    unique = SimpleNamespace(orig=SimpleNamespace(sqlstate="23505"))
    other = SimpleNamespace(orig=SimpleNamespace(sqlstate="23503"))  # FK violation
    assert is_unique_violation(unique) is True  # type: ignore[arg-type]
    assert is_unique_violation(other) is False  # type: ignore[arg-type]
    # A bare exception with no driver code is not a unique violation.
    assert is_unique_violation(RuntimeError("no sqlstate")) is False


def test_create_database_composes_engine_and_sessionmaker() -> None:
    database = create_database(_DSN)
    assert isinstance(database, Database)
    # Engine construction is lazy: no connection is opened here.
    assert database.engine.url.database == "floresu"


async def test_get_session_yields_a_request_scoped_session() -> None:
    database = create_database(_DSN)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=database)))
    generator = get_session(request)  # type: ignore[arg-type]
    session = await anext(generator)
    try:
        assert isinstance(session, AsyncSession)
    finally:
        # Resume past the yield so the `async with` session context exits (the
        # session is closed) and the generator completes.
        with pytest.raises(StopAsyncIteration):
            await anext(generator)
        await database.engine.dispose()


async def test_readiness_check_reports_a_connection_failure_as_not_ready() -> None:
    class _FailingConn:
        async def __aenter__(self) -> object:
            raise OSError("connection refused")

        async def __aexit__(self, *_: object) -> bool:
            return False

    class _FailingEngine:
        def connect(self) -> _FailingConn:
            return _FailingConn()

    result = await db_readiness_check(_FailingEngine())()  # type: ignore[arg-type]
    assert result.name == "postgres"
    assert result.ok is False
    assert "connection refused" in (result.detail or "")


async def test_db_lifespan_disposes_the_pool_on_shutdown() -> None:
    engine = create_db_engine(_DSN)
    sessionmaker = create_sessionmaker(engine)
    assert sessionmaker is not None
    lifespan = create_db_lifespan(engine)
    async with lifespan(FastAPI()):
        pass
    # dispose() is idempotent; a second call after lifespan shutdown must not raise.
    await engine.dispose()


class _NoQuerySession:
    """A session stand-in whose ``execute`` must never run (short-circuit guard)."""

    async def execute(self, *_: object) -> object:
        raise AssertionError("owned_ids must not query when candidate_ids is empty")


async def test_owned_ids_short_circuits_without_a_query_for_empty_candidate_ids() -> None:
    # The empty guard returns before touching the session, so a live query is never
    # issued for a write that frames nothing.
    result = await owned_ids(
        _NoQuerySession(),  # type: ignore[arg-type]
        user_pk_column=Source.user_id,
        id_column=Source.id,
        user_pk=1,
        candidate_ids=[],
    )
    assert result == set()


def test_group_pairs_into_dict_groups_values_in_input_order() -> None:
    grouped = group_pairs_into_dict([(1, "a"), (2, "b"), (1, "c"), (2, "d"), (1, "e")])
    assert grouped == {1: ["a", "c", "e"], 2: ["b", "d"]}
    # Keys keep first-seen order, mirroring an ordered edge read.
    assert list(grouped) == [1, 2]


def test_group_pairs_into_dict_keeps_duplicate_values_without_dedup() -> None:
    grouped = group_pairs_into_dict([(1, 7), (1, 7), (1, 8)])
    assert grouped == {1: [7, 7, 8]}


def test_group_pairs_into_dict_returns_empty_for_no_rows() -> None:
    rows: list[tuple[int, str]] = []
    assert group_pairs_into_dict(rows) == {}
