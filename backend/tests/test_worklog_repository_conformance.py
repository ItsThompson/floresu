"""Repository conformance for the worklog domain: one contract, both backends.

Runs the worklog behavioral contract (archived-excluding bullet join, timeline
ordering, owner scoping, tag dedup) against both the in-memory fake and the
SQLAlchemy binding, so a query change that diverges from production fails the unit
lane. The ``SAVEPOINT``/``begin_nested`` recovery of ``get_or_create_tag`` has no
cross-backend contract, so it is asserted on the SQLAlchemy lane alone.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Protocol

import pytest
from sqlalchemy import func, select

from floresu.accounts.models import User
from floresu.core.db import transaction
from floresu.library.models import Bulletpoint, BulletWorklog
from floresu.worklog.models import Tag, WorklogEntry
from floresu.worklog.repository import SqlAlchemyWorklogRepository, WorklogRepository
from tests.support.conformance import (
    Arranger,
    RepoCase,
    backend_params,
    sqlalchemy_backend,
)
from tests.worklog_fakes import InMemoryWorklogRepository

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class WorklogArranger(Arranger, Protocol):
    """Seed worklog entries and the bullets that frame them, on either backend."""

    async def seed_entry(self, user_pk: int, *, title: str, entry_date: date) -> int: ...

    async def frame_bullet(self, user_pk: int, worklog_id: int, *, archived: bool) -> int: ...


WorklogCase = RepoCase[WorklogRepository, WorklogArranger]


class InMemoryWorklogArranger:
    """Seeds the in-memory fake: minted ids and framed bullets, no database."""

    def __init__(self, repo: InMemoryWorklogRepository) -> None:
        self._repo = repo
        self._next_user_pk = 1
        self._next_bullet_id = 1

    async def own_user(self) -> int:
        pk = self._next_user_pk
        self._next_user_pk += 1
        return pk

    async def seed_entry(self, user_pk: int, *, title: str, entry_date: date) -> int:
        entry = WorklogEntry(
            user_id=user_pk, title=title, entry_date=entry_date, content_hash="seed"
        )
        await self._repo.add(entry)
        return entry.id

    async def frame_bullet(self, user_pk: int, worklog_id: int, *, archived: bool) -> int:
        bullet_id = self._next_bullet_id
        self._next_bullet_id += 1
        self._repo.frame_bullet(worklog_id, bullet_id, archived=archived)
        return bullet_id


class SqlAlchemyWorklogArranger:
    """Seeds real rows: an account, its entries, and the framing bullets + edges."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def own_user(self) -> int:
        async with self._sessionmaker() as session, transaction(session):
            user = User(email=f"conf-wl-{uuid.uuid4().hex}@example.com", password_hash="x")
            session.add(user)
            await session.flush()
            return user.id

    async def seed_entry(self, user_pk: int, *, title: str, entry_date: date) -> int:
        async with self._sessionmaker() as session, transaction(session):
            entry = WorklogEntry(
                user_id=user_pk, title=title, entry_date=entry_date, content_hash="seed"
            )
            session.add(entry)
            await session.flush()
            return entry.id

    async def frame_bullet(self, user_pk: int, worklog_id: int, *, archived: bool) -> int:
        async with self._sessionmaker() as session, transaction(session):
            bullet = Bulletpoint(
                user_id=user_pk,
                text="framing bullet",
                content_hash="seed",
                archived_at=datetime.now(UTC) if archived else None,
            )
            session.add(bullet)
            await session.flush()
            session.add(BulletWorklog(bullet_id=bullet.id, worklog_id=worklog_id))
            return bullet.id


def in_memory_worklog_case() -> WorklogCase:
    fake = InMemoryWorklogRepository()
    repo: WorklogRepository = fake
    arrange: WorklogArranger = InMemoryWorklogArranger(fake)
    return RepoCase(repo=repo, arrange=arrange, lane="unit")


async def _sqlalchemy_worklog_case(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[WorklogCase]:
    async with sessionmaker() as read_session:
        repo: WorklogRepository = SqlAlchemyWorklogRepository(read_session)
        arrange: WorklogArranger = SqlAlchemyWorklogArranger(sessionmaker)
        yield RepoCase(repo=repo, arrange=arrange, lane="integration")


@pytest.fixture(params=backend_params())
async def worklog_case(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[WorklogCase]:
    if request.param == "in_memory":
        yield in_memory_worklog_case()
        return
    postgres_url: str = request.getfixturevalue("postgres_url")
    async with sqlalchemy_backend(postgres_url, monkeypatch) as sessionmaker:
        async for case in _sqlalchemy_worklog_case(sessionmaker):
            yield case


async def test_bullet_ids_by_worklog_excludes_archived(worklog_case: WorklogCase) -> None:
    user_pk = await worklog_case.arrange.own_user()
    worklog_id = await worklog_case.arrange.seed_entry(
        user_pk, title="Shipped the search API", entry_date=date(2026, 1, 15)
    )
    active = await worklog_case.arrange.frame_bullet(user_pk, worklog_id, archived=False)
    await worklog_case.arrange.frame_bullet(user_pk, worklog_id, archived=True)

    result = await worklog_case.repo.bullet_ids_by_worklog([worklog_id])

    assert result == {worklog_id: [active]}


async def test_list_entries_orders_by_date_then_id_desc(worklog_case: WorklogCase) -> None:
    user_pk = await worklog_case.arrange.own_user()
    older = await worklog_case.arrange.seed_entry(
        user_pk, title="older", entry_date=date(2026, 1, 10)
    )
    same_day_first = await worklog_case.arrange.seed_entry(
        user_pk, title="same-day-first", entry_date=date(2026, 1, 20)
    )
    same_day_second = await worklog_case.arrange.seed_entry(
        user_pk, title="same-day-second", entry_date=date(2026, 1, 20)
    )

    entries = await worklog_case.repo.list_entries(user_pk, include_archived=False, limit=10)

    assert [entry.id for entry in entries] == [same_day_second, same_day_first, older]


async def test_get_is_scoped_to_the_owner(worklog_case: WorklogCase) -> None:
    owner = await worklog_case.arrange.own_user()
    other = await worklog_case.arrange.own_user()
    worklog_id = await worklog_case.arrange.seed_entry(
        owner, title="mine", entry_date=date(2026, 1, 15)
    )

    assert await worklog_case.repo.get(owner, worklog_id) is not None
    assert await worklog_case.repo.get(other, worklog_id) is None


async def test_get_or_create_tag_reuses_an_existing_label(worklog_case: WorklogCase) -> None:
    user_pk = await worklog_case.arrange.own_user()

    first = await worklog_case.repo.get_or_create_tag(user_pk, "api")
    second = await worklog_case.repo.get_or_create_tag(user_pk, "api")

    assert first.id == second.id
    tags = await worklog_case.repo.list_tags(user_pk)
    assert [tag.label for tag in tags] == ["api"]


@pytest.fixture
async def worklog_sessionmaker(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    async with sqlalchemy_backend(postgres_url, monkeypatch) as sessionmaker:
        yield sessionmaker


@pytest.mark.integration
async def test_get_or_create_tag_recovers_from_a_concurrent_duplicate(
    worklog_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with worklog_sessionmaker() as session, transaction(session):
        user = User(email=f"conf-wl-{uuid.uuid4().hex}@example.com", password_hash="x")
        session.add(user)
        await session.flush()
        user_pk = user.id

    async def get_or_create() -> int:
        async with worklog_sessionmaker() as session, transaction(session):
            repo = SqlAlchemyWorklogRepository(session)
            tag = await repo.get_or_create_tag(user_pk, "concurrent")
            return tag.id

    # A same-label race: the loser's nested INSERT breaches uq_tags_user_id, and the
    # SAVEPOINT keeps its transaction usable to refetch the winner's committed row.
    first_id, second_id = await asyncio.gather(get_or_create(), get_or_create())

    assert first_id == second_id
    async with worklog_sessionmaker() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(Tag)
            .where(Tag.user_id == user_pk, Tag.label == "concurrent")
        )
    assert count == 1
