"""Repository conformance for the search domain: the pgvector semantic contract.

pgvector cosine similarity has no cross-backend contract (the in-memory search
double returns a seeded hit order, not a vector ranking), so per the harness design
it is asserted on the SQLAlchemy lane alone: the semantic retriever orders an
account's bullets nearest-first by cosine distance to the query vector. This whole
module is therefore ``integration``-marked and skips without Docker.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from floresu.accounts.models import User
from floresu.core.db import transaction
from floresu.embedding.config import EMBEDDING_DIMENSION, EMBEDDING_MODEL, EmbedItemKind
from floresu.embedding.models import Embedding
from floresu.library.models import Bulletpoint
from floresu.search.retrieval import SqlAlchemySearchRepository
from floresu.search.schemas import SearchFilters
from tests.support.conformance import sqlalchemy_backend

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


def _unit_vector(axis: int) -> list[float]:
    """A one-hot vector along ``axis`` in the pinned embedding dimension."""
    vector = [0.0] * EMBEDDING_DIMENSION
    vector[axis] = 1.0
    return vector


class SqlAlchemySearchArranger:
    """Seeds a bullet plus its stored embedding vector for an account."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def own_user(self) -> int:
        async with self._sessionmaker() as session, transaction(session):
            user = User(email=f"conf-search-{uuid.uuid4().hex}@example.com", password_hash="x")
            session.add(user)
            await session.flush()
            return user.id

    async def seed_bullet_vector(self, user_pk: int, vector: list[float]) -> int:
        async with self._sessionmaker() as session, transaction(session):
            bullet = Bulletpoint(user_id=user_pk, text="framing bullet", content_hash="seed")
            session.add(bullet)
            await session.flush()
            session.add(
                Embedding(
                    item_kind=EmbedItemKind.BULLET,
                    item_id=bullet.id,
                    user_id=user_pk,
                    content_hash="seed",
                    vector=vector,
                    model=EMBEDDING_MODEL,
                )
            )
            return bullet.id


@pytest.fixture
async def search_sessionmaker(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    async with sqlalchemy_backend(postgres_url, monkeypatch) as sessionmaker:
        yield sessionmaker


async def test_semantic_orders_bullets_nearest_first_by_cosine(
    search_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    arrange = SqlAlchemySearchArranger(search_sessionmaker)
    user_pk = await arrange.own_user()
    near = await arrange.seed_bullet_vector(user_pk, _unit_vector(0))
    far = await arrange.seed_bullet_vector(user_pk, _unit_vector(1))

    async with search_sessionmaker() as session:
        hits = await SqlAlchemySearchRepository(session).semantic(
            user_pk,
            _unit_vector(0),
            SearchFilters(),
            frozenset({EmbedItemKind.BULLET}),
            limit=10,
        )

    # The query vector coincides with ``near`` (cosine distance 0) and is orthogonal
    # to ``far`` (distance 1), so the nearest bullet ranks first.
    assert [hit.item_id for hit in hits] == [near, far]
