"""Repository conformance for the library domain: one contract, both backends.

Runs the canonical-bullet contract (the compare-and-swap on ``revision`` and owner
scoping) against both the in-memory fake and the SQLAlchemy binding. The true
optimistic-lock loss (two writers that loaded the same revision, one of which must
match zero rows) is a concurrency race with no cross-backend contract, so it is
asserted on the SQLAlchemy lane alone.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Protocol

import pytest

from floresu.accounts.models import User
from floresu.core.db import transaction
from floresu.library.models import Bulletpoint
from floresu.library.repository import LibraryRepository, SqlAlchemyLibraryRepository
from tests.library_fakes import InMemoryLibraryRepository
from tests.support.conformance import (
    Arranger,
    RepoCase,
    backend_params,
    resolve_case,
    sqlalchemy_backend,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class LibraryArranger(Arranger, Protocol):
    """Seed a canonical bullet at revision 1, on either backend."""

    async def seed_bullet(self, user_pk: int, *, text: str) -> int: ...


LibraryCase = RepoCase[LibraryRepository, LibraryArranger]


class InMemoryLibraryArranger:
    """Seeds the in-memory fake: minted ids, no database."""

    def __init__(self, repo: InMemoryLibraryRepository) -> None:
        self._repo = repo
        self._next_user_pk = 1

    async def own_user(self) -> int:
        pk = self._next_user_pk
        self._next_user_pk += 1
        return pk

    async def seed_bullet(self, user_pk: int, *, text: str) -> int:
        bullet = Bulletpoint(user_id=user_pk, text=text, content_hash="seed", revision=1)
        await self._repo.add(bullet)
        return bullet.id


class SqlAlchemyLibraryArranger:
    """Seeds real ``bulletpoints`` rows for an account."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def own_user(self) -> int:
        async with self._sessionmaker() as session, transaction(session):
            user = User(email=f"conf-lib-{uuid.uuid4().hex}@example.com", password_hash="x")
            session.add(user)
            await session.flush()
            return user.id

    async def seed_bullet(self, user_pk: int, *, text: str) -> int:
        async with self._sessionmaker() as session, transaction(session):
            bullet = Bulletpoint(user_id=user_pk, text=text, content_hash="seed")
            session.add(bullet)
            await session.flush()
            return bullet.id


def in_memory_library_case() -> LibraryCase:
    fake = InMemoryLibraryRepository()
    repo: LibraryRepository = fake
    arrange: LibraryArranger = InMemoryLibraryArranger(fake)
    return RepoCase(repo=repo, arrange=arrange, lane="unit")


async def _sqlalchemy_library_case(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[LibraryCase]:
    async with sessionmaker() as read_session:
        repo: LibraryRepository = SqlAlchemyLibraryRepository(read_session)
        arrange: LibraryArranger = SqlAlchemyLibraryArranger(sessionmaker)
        yield RepoCase(repo=repo, arrange=arrange, lane="integration")


@pytest.fixture(params=backend_params())
async def library_case(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[LibraryCase]:
    async for case in resolve_case(
        request,
        monkeypatch,
        in_memory=in_memory_library_case,
        sqlalchemy=_sqlalchemy_library_case,
    ):
        yield case


async def test_cas_advances_the_revision_on_a_matching_token(library_case: LibraryCase) -> None:
    user_pk = await library_case.arrange.own_user()
    bullet_id = await library_case.arrange.seed_bullet(user_pk, text="before")

    won = await library_case.repo.update_text_if_revision(user_pk, bullet_id, 1, "after", "hash-2")

    assert won is True
    updated = await library_case.repo.get(user_pk, bullet_id)
    assert updated is not None
    assert updated.revision == 2
    assert updated.text == "after"


async def test_cas_rejects_a_stale_token(library_case: LibraryCase) -> None:
    user_pk = await library_case.arrange.own_user()
    bullet_id = await library_case.arrange.seed_bullet(user_pk, text="before")
    await library_case.repo.update_text_if_revision(user_pk, bullet_id, 1, "after", "hash-2")

    # The token 1 has moved on to 2, so a second write with the stale token loses.
    lost = await library_case.repo.update_text_if_revision(user_pk, bullet_id, 1, "again", "hash-3")

    assert lost is False


async def test_cas_is_scoped_to_the_owner(library_case: LibraryCase) -> None:
    owner = await library_case.arrange.own_user()
    other = await library_case.arrange.own_user()
    bullet_id = await library_case.arrange.seed_bullet(owner, text="before")

    assert await library_case.repo.get(other, bullet_id) is None
    assert await library_case.repo.update_text_if_revision(other, bullet_id, 1, "x", "h") is False


@pytest.fixture
async def library_sessionmaker(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    async with sqlalchemy_backend(postgres_url, monkeypatch) as sessionmaker:
        yield sessionmaker


@pytest.mark.integration
async def test_cas_resolves_a_concurrent_same_revision_race(
    library_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with library_sessionmaker() as session, transaction(session):
        user = User(email=f"conf-lib-{uuid.uuid4().hex}@example.com", password_hash="x")
        session.add(user)
        await session.flush()
        user_pk = user.id
        bullet = Bulletpoint(user_id=user_pk, text="before", content_hash="seed")
        session.add(bullet)
        await session.flush()
        bullet_id = bullet.id

    async def cas(text: str) -> bool:
        async with library_sessionmaker() as session, transaction(session):
            repo = SqlAlchemyLibraryRepository(session)
            return await repo.update_text_if_revision(user_pk, bullet_id, 1, text, "hash")

    # Both writers loaded revision 1; the database lets exactly one match and
    # increment, the loser matches zero rows.
    first, second = await asyncio.gather(cas("A"), cas("B"))

    assert {first, second} == {True, False}
    async with library_sessionmaker() as session:
        winner = await session.get(Bulletpoint, bullet_id)
    assert winner is not None
    assert winner.revision == 2
