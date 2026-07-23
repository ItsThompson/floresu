"""Repository conformance for the resume domain: one contract, both backends.

Runs the resume-list contract (the ``kind`` filter and owner scoping) against both
the in-memory fake and the SQLAlchemy binding, so a filter that diverges from the
real ``WHERE kind = ?`` fails the unit lane.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Protocol

import pytest

from floresu.accounts.models import User
from floresu.core.db import transaction
from floresu.resumes.models import Resume, ResumeKind
from floresu.resumes.repository import ResumeRepository, SqlAlchemyResumeRepository
from tests.resumes_fakes import InMemoryResumeRepository
from tests.support.conformance import Arranger, RepoCase, backend_params, sqlalchemy_backend

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class ResumeArranger(Arranger, Protocol):
    """Seed a resume of a given kind, on either backend."""

    async def seed_resume(self, user_pk: int, *, kind: ResumeKind) -> int: ...


ResumeCase = RepoCase[ResumeRepository, ResumeArranger]


def _new_resume(user_pk: int, kind: ResumeKind) -> Resume:
    return Resume(
        user_id=user_pk, kind=kind, title="Backend Engineer", schema_version=1, document={}
    )


class InMemoryResumeArranger:
    """Seeds the in-memory fake: minted ids, no database."""

    def __init__(self, repo: InMemoryResumeRepository) -> None:
        self._repo = repo
        self._next_user_pk = 1

    async def own_user(self) -> int:
        pk = self._next_user_pk
        self._next_user_pk += 1
        return pk

    async def seed_resume(self, user_pk: int, *, kind: ResumeKind) -> int:
        resume = _new_resume(user_pk, kind)
        await self._repo.add(resume)
        return resume.id


class SqlAlchemyResumeArranger:
    """Seeds real ``resumes`` rows for an account."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def own_user(self) -> int:
        async with self._sessionmaker() as session, transaction(session):
            user = User(email=f"conf-res-{uuid.uuid4().hex}@example.com", password_hash="x")
            session.add(user)
            await session.flush()
            return user.id

    async def seed_resume(self, user_pk: int, *, kind: ResumeKind) -> int:
        async with self._sessionmaker() as session, transaction(session):
            resume = _new_resume(user_pk, kind)
            session.add(resume)
            await session.flush()
            return resume.id


def in_memory_resume_case() -> ResumeCase:
    fake = InMemoryResumeRepository()
    repo: ResumeRepository = fake
    arrange: ResumeArranger = InMemoryResumeArranger(fake)
    return RepoCase(repo=repo, arrange=arrange, lane="unit")


async def _sqlalchemy_resume_case(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[ResumeCase]:
    async with sessionmaker() as read_session:
        repo: ResumeRepository = SqlAlchemyResumeRepository(read_session)
        arrange: ResumeArranger = SqlAlchemyResumeArranger(sessionmaker)
        yield RepoCase(repo=repo, arrange=arrange, lane="integration")


@pytest.fixture(params=backend_params())
async def resume_case(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[ResumeCase]:
    if request.param == "in_memory":
        yield in_memory_resume_case()
        return
    postgres_url: str = request.getfixturevalue("postgres_url")
    async with sqlalchemy_backend(postgres_url, monkeypatch) as sessionmaker:
        async for case in _sqlalchemy_resume_case(sessionmaker):
            yield case


async def test_list_resumes_filters_by_kind(resume_case: ResumeCase) -> None:
    user_pk = await resume_case.arrange.own_user()
    living = await resume_case.arrange.seed_resume(user_pk, kind=ResumeKind.LIVING)
    application = await resume_case.arrange.seed_resume(user_pk, kind=ResumeKind.APPLICATION)

    living_only = await resume_case.repo.list_resumes(
        user_pk, kind=ResumeKind.LIVING, include_archived=False, limit=10
    )
    application_only = await resume_case.repo.list_resumes(
        user_pk, kind=ResumeKind.APPLICATION, include_archived=False, limit=10
    )
    unfiltered = await resume_case.repo.list_resumes(
        user_pk, kind=None, include_archived=False, limit=10
    )

    assert [resume.id for resume in living_only] == [living]
    assert [resume.id for resume in application_only] == [application]
    # No kind filter returns both, newest-first (id descending).
    assert [resume.id for resume in unfiltered] == [application, living]


async def test_list_resumes_is_scoped_to_the_owner(resume_case: ResumeCase) -> None:
    owner = await resume_case.arrange.own_user()
    other = await resume_case.arrange.own_user()
    await resume_case.arrange.seed_resume(owner, kind=ResumeKind.LIVING)

    other_list = await resume_case.repo.list_resumes(
        other, kind=None, include_archived=False, limit=10
    )

    assert other_list == []
