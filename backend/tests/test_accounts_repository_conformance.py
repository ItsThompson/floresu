"""Repository conformance for the accounts domain: one contract, both backends.

Runs the identity-mapping contract (``get_by_id`` maps the string wire identity to
the bigint PK, resolving a non-numeric or missing id to ``None``) against both the
in-memory fake and the SQLAlchemy binding. The ``on_conflict`` idempotence of
``revoke_session`` is a Postgres upsert semantic with no cross-backend contract, so
it is asserted on the SQLAlchemy lane alone.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Protocol

import pytest
from sqlalchemy import func, select

from floresu.accounts.models import RevokedSession, User
from floresu.accounts.repository import AccountRepository, SqlAlchemyAccountRepository
from floresu.accounts.tokens import RefreshClaims
from floresu.core.db import transaction
from tests.accounts_fakes import InMemoryAccountRepository
from tests.support.conformance import Arranger, RepoCase, backend_params, sqlalchemy_backend

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class AccountArranger(Arranger, Protocol):
    """Seed an account, on either backend (``own_user`` is the whole contract)."""


AccountCase = RepoCase[AccountRepository, AccountArranger]


class InMemoryAccountArranger:
    """Seeds the in-memory fake through its own ``add_user`` (real uniqueness + id)."""

    def __init__(self, repo: InMemoryAccountRepository) -> None:
        self._repo = repo

    async def own_user(self) -> int:
        user = User(email=f"conf-acct-{uuid.uuid4().hex}@example.com", password_hash="x")
        await self._repo.add_user(user)
        return user.id


class SqlAlchemyAccountArranger:
    """Seeds real ``users`` rows."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def own_user(self) -> int:
        async with self._sessionmaker() as session, transaction(session):
            user = User(email=f"conf-acct-{uuid.uuid4().hex}@example.com", password_hash="x")
            session.add(user)
            await session.flush()
            return user.id


def in_memory_account_case() -> AccountCase:
    fake = InMemoryAccountRepository()
    repo: AccountRepository = fake
    arrange: AccountArranger = InMemoryAccountArranger(fake)
    return RepoCase(repo=repo, arrange=arrange, lane="unit")


async def _sqlalchemy_account_case(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AccountCase]:
    async with sessionmaker() as read_session:
        repo: AccountRepository = SqlAlchemyAccountRepository(read_session)
        arrange: AccountArranger = SqlAlchemyAccountArranger(sessionmaker)
        yield RepoCase(repo=repo, arrange=arrange, lane="integration")


@pytest.fixture(params=backend_params())
async def account_case(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AccountCase]:
    if request.param == "in_memory":
        yield in_memory_account_case()
        return
    postgres_url: str = request.getfixturevalue("postgres_url")
    async with sqlalchemy_backend(postgres_url, monkeypatch) as sessionmaker:
        async for case in _sqlalchemy_account_case(sessionmaker):
            yield case


async def test_get_by_id_maps_the_string_identity_to_the_pk(account_case: AccountCase) -> None:
    user_pk = await account_case.arrange.own_user()

    found = await account_case.repo.get_by_id(str(user_pk))

    assert found is not None
    assert found.id == user_pk


async def test_get_by_id_resolves_a_non_numeric_identity_to_none(account_case: AccountCase) -> None:
    await account_case.arrange.own_user()

    assert await account_case.repo.get_by_id("not-a-number") is None


async def test_get_by_id_resolves_a_missing_id_to_none(account_case: AccountCase) -> None:
    user_pk = await account_case.arrange.own_user()

    assert await account_case.repo.get_by_id(str(user_pk + 1_000_000)) is None


@pytest.fixture
async def account_sessionmaker(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    async with sqlalchemy_backend(postgres_url, monkeypatch) as sessionmaker:
        yield sessionmaker


@pytest.mark.integration
async def test_revoke_session_is_idempotent(
    account_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with account_sessionmaker() as session, transaction(session):
        user = User(email=f"conf-acct-{uuid.uuid4().hex}@example.com", password_hash="x")
        session.add(user)
        await session.flush()
        user_pk = user.id

    claims = RefreshClaims(
        user_id=str(user_pk),
        sid=f"s-{uuid.uuid4().hex[:20]}",
        expires_at=datetime.now(UTC) + timedelta(days=14),
    )

    # Revoke twice: the second insert hits ON CONFLICT DO NOTHING, not a duplicate.
    for _ in range(2):
        async with account_sessionmaker() as session, transaction(session):
            await SqlAlchemyAccountRepository(session).revoke_session(claims)

    async with account_sessionmaker() as session:
        rows = await session.scalar(
            select(func.count()).select_from(RevokedSession).where(RevokedSession.sid == claims.sid)
        )
        revoked = await SqlAlchemyAccountRepository(session).is_session_revoked(claims.sid)

    assert rows == 1
    assert revoked is True
