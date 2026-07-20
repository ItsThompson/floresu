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
    is_unique_violation,
    transaction,
)

_DSN = "postgresql+asyncpg://floresu:floresu@localhost:5432/floresu"


class _SpySession:
    """Records commit/rollback so the transaction boundary is verifiable offline."""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

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
