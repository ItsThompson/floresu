"""Repository conformance harness: one behavioral contract, both backends.

A conformance suite parametrizes a repository ``Protocol`` over its in-memory fake
and its SQLAlchemy binding, so a query change that diverges from production fails
the unit lane instead of hiding until a Docker-gated integration run. Each domain
provides an :class:`Arranger` that seeds the state a contract needs against
whichever backend is live, and two :class:`RepoCase` factories (in-memory and
SQLAlchemy).

The in-memory parameter runs in the unit lane; the SQLAlchemy parameter carries
the ``integration`` marker (see :func:`backend_params`) so ``-m "not integration"``
collects only the in-memory parameter and the SQLAlchemy parameter runs Docker-up
and skips without Docker through the ``postgres_url`` fixture.

Postgres-only semantics (``on_conflict`` idempotence, ``SAVEPOINT``/``begin_nested``,
pgvector, a true optimistic-lock loss) have no cross-backend contract, so they are
asserted by ``integration``-marked tests on the SQLAlchemy lane alone rather than
through the parametrized case.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

import pytest
from alembic import command
from alembic.config import Config

from floresu.core.db import create_db_engine, create_sessionmaker

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from _pytest.mark.structures import ParameterSet
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# The lane a parametrized case runs in: the in-memory fake in the unit lane, the
# SQLAlchemy binding in the Docker-gated integration lane.
Lane = Literal["unit", "integration"]

# tests/support/conformance.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Arranger(Protocol):
    """Seed the state a conformance case needs, against whichever backend is live.

    The seam that lets one contract run on both backends: the in-memory arranger
    seeds through the fake's own methods, while the SQLAlchemy arranger inserts real
    rows plus the foreign-table rows a real query joins. Every domain seeds an
    account, so :meth:`own_user` is the one shared method; each domain's arranger
    subtype adds the seed methods its contract needs.
    """

    async def own_user(self) -> int:
        """Seed an account and return its (backend-minted) primary key."""
        ...


@dataclass
class RepoCase[R, A: Arranger]:
    """One parametrized backend: the repository under test plus its arranger.

    ``repo`` is the in-memory fake or the SQLAlchemy binding, ``arrange`` seeds the
    matching backend, and ``lane`` names the lane this parameter runs in. Generic
    over the arranger as well as the repository so a domain's seed methods stay
    statically typed at the call site under ``mypy --strict``.
    """

    repo: R
    arrange: A
    lane: Lane


def backend_params() -> list[ParameterSet]:
    """The ``[in_memory, sqlalchemy]`` parametrization for a conformance fixture.

    Only the SQLAlchemy parameter carries the ``integration`` marker, so the unit
    lane (``-m "not integration"``) collects the in-memory parameter alone and the
    integration lane collects the SQLAlchemy parameter, which skips without Docker
    through the ``postgres_url`` fixture.
    """
    return [
        pytest.param("in_memory", id="in_memory"),
        pytest.param("sqlalchemy", id="sqlalchemy", marks=pytest.mark.integration),
    ]


def migrate() -> None:
    """Apply every Alembic migration to the database in ``DATABASE_URL``.

    Idempotent at head, so a suite that migrates the shared session-scoped
    container more than once pays only the version-check cost after the first run.
    The Alembic env reads the URL from ``DATABASE_URL``; the caller sets it (via
    ``monkeypatch``) before calling. Runs a private event loop internally, so call
    it off-loop (see :func:`sqlalchemy_backend`).
    """
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")


@contextlib.asynccontextmanager
async def sqlalchemy_backend(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Point the env at the live Postgres, migrate, and yield a session factory.

    The one place a conformance fixture wires the SQLAlchemy lane: it sets
    ``DATABASE_URL``, runs the migration in a worker thread (the Alembic env drives
    its own ``asyncio.run``, which cannot nest inside the test's running loop), and
    yields a session factory whose pool is disposed on exit.
    """
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    await asyncio.to_thread(migrate)
    engine = create_db_engine(postgres_url)
    try:
        yield create_sessionmaker(engine)
    finally:
        await engine.dispose()


async def resolve_case[R, A: Arranger](
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    *,
    in_memory: Callable[[], RepoCase[R, A]],
    sqlalchemy: Callable[[async_sessionmaker[AsyncSession]], AsyncIterator[RepoCase[R, A]]],
) -> AsyncIterator[RepoCase[R, A]]:
    """Yield the case for the current parameter: in-memory fake or SQLAlchemy binding.

    The shared body of every domain's parametrized ``*_case`` fixture: the
    in-memory parameter yields ``in_memory()`` in the unit lane; the SQLAlchemy
    parameter resolves the Docker-gated ``postgres_url`` (skipping without Docker),
    opens a migrated backend, and drives the domain's ``sqlalchemy`` builder, whose
    session stays open for the test.
    """
    if request.param == "in_memory":
        yield in_memory()
        return
    postgres_url: str = request.getfixturevalue("postgres_url")
    async with sqlalchemy_backend(postgres_url, monkeypatch) as sessionmaker:
        async for case in sqlalchemy(sessionmaker):
            yield case
