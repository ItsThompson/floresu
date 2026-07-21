"""Integration tests for the embeddings repository against real Postgres.

Exercises the ``vector(1536)`` round-trip and the ``ON CONFLICT`` upsert over a
live pgvector database: an insert, an idempotent overwrite that replaces the
vector/hash/model in place (one row, not two), and an idempotent delete.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config

from floresu.accounts.models import User
from floresu.core.db import create_db_engine, create_sessionmaker, transaction
from floresu.embedding.config import EMBEDDING_DIMENSION, EmbedItemKind
from floresu.embedding.repository import SqlAlchemyEmbeddingRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]
_WORKLOG = EmbedItemKind.WORKLOG


@pytest.fixture
def sessionmaker(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> async_sessionmaker[AsyncSession]:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")
    return create_sessionmaker(create_db_engine(postgres_url))


async def _insert_user(sessionmaker: async_sessionmaker[AsyncSession], email: str) -> int:
    async with sessionmaker() as session, transaction(session):
        user = User(email=email, password_hash="x")
        session.add(user)
        await session.flush()
        return user.id


def _vector(fill: float) -> list[float]:
    return [fill] * EMBEDDING_DIMENSION


async def test_upsert_inserts_then_reads_back_the_vector(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _insert_user(sessionmaker, "embed-repo-1@test.dev")
    async with sessionmaker() as session, transaction(session):
        repo = SqlAlchemyEmbeddingRepository(session)
        await repo.upsert(
            user_id=user_id,
            kind=_WORKLOG,
            item_id=1,
            content_hash="h1",
            vector=_vector(0.25),
            model="text-embedding-3-small",
        )

    async with sessionmaker() as session:
        stored = await SqlAlchemyEmbeddingRepository(session).get(_WORKLOG, 1)
    assert stored is not None
    assert stored.content_hash == "h1"
    assert stored.model == "text-embedding-3-small"
    assert len(list(stored.vector)) == EMBEDDING_DIMENSION
    assert float(stored.vector[0]) == pytest.approx(0.25)


async def test_upsert_overwrites_in_place(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _insert_user(sessionmaker, "embed-repo-2@test.dev")
    async with sessionmaker() as session, transaction(session):
        repo = SqlAlchemyEmbeddingRepository(session)
        await repo.upsert(
            user_id=user_id,
            kind=_WORKLOG,
            item_id=1,
            content_hash="h1",
            vector=_vector(0.1),
            model="m1",
        )
    async with sessionmaker() as session:
        first = await SqlAlchemyEmbeddingRepository(session).get(_WORKLOG, 1)
    assert first is not None
    first_updated_at = first.updated_at
    async with sessionmaker() as session, transaction(session):
        repo = SqlAlchemyEmbeddingRepository(session)
        await repo.upsert(
            user_id=user_id,
            kind=_WORKLOG,
            item_id=1,
            content_hash="h2",
            vector=_vector(0.9),
            model="m2",
        )

    async with sessionmaker() as session:
        stored = await SqlAlchemyEmbeddingRepository(session).get(_WORKLOG, 1)
    assert stored is not None
    assert stored.content_hash == "h2"
    assert stored.model == "m2"
    assert float(stored.vector[0]) == pytest.approx(0.9)
    # The re-embed refreshes updated_at (the moment the vector was produced), so it
    # advances past the first insert's stamp rather than freezing.
    assert stored.updated_at > first_updated_at


async def test_delete_removes_the_row_and_is_idempotent(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _insert_user(sessionmaker, "embed-repo-3@test.dev")
    async with sessionmaker() as session, transaction(session):
        await SqlAlchemyEmbeddingRepository(session).upsert(
            user_id=user_id,
            kind=_WORKLOG,
            item_id=1,
            content_hash="h1",
            vector=_vector(0.5),
            model="m",
        )
    async with sessionmaker() as session, transaction(session):
        await SqlAlchemyEmbeddingRepository(session).delete(_WORKLOG, 1)
    # A second delete of a now-absent row is a no-op.
    async with sessionmaker() as session, transaction(session):
        await SqlAlchemyEmbeddingRepository(session).delete(_WORKLOG, 1)

    async with sessionmaker() as session:
        assert await SqlAlchemyEmbeddingRepository(session).get(_WORKLOG, 1) is None
