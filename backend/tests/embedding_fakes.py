"""In-memory test doubles for the embedding pipeline.

The service is tested sociably: the real :class:`EmbeddingService` and the pure
gate run over these doubles, which stand in only at true external boundaries
(Postgres via the in-memory repository and corpus, OpenAI via the fake provider,
Redis/arq via the recording queue). No test ever calls OpenAI or a live broker.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from floresu.embedding.config import EMBEDDING_DIMENSION, EMBEDDING_MODEL, EmbedItemKind
from floresu.embedding.corpus import CorpusResolver
from floresu.embedding.models import Embedding
from floresu.embedding.schemas import CorpusItem

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class FakeSession:
    """A no-op stand-in for ``AsyncSession`` recording the transaction boundary.

    Carries ``info`` because the ``transaction`` boundary drains the session's
    post-commit queue on a clean exit.
    """

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.info: dict[str, Any] = {}

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeCorpusResolver(CorpusResolver):
    """A resolver returning seeded corpus items, keyed by ``(kind, item_id)``."""

    def __init__(self) -> None:
        self._items: dict[tuple[EmbedItemKind, int], CorpusItem] = {}

    def seed(self, kind: EmbedItemKind, item_id: int, item: CorpusItem) -> None:
        self._items[(kind, item_id)] = item

    async def resolve(
        self, session: AsyncSession, user_id: int, kind: EmbedItemKind, item_id: int
    ) -> CorpusItem | None:
        return self._items.get((kind, item_id))


class FakeEmbeddingProvider:
    """A provider that returns deterministic vectors and records its calls."""

    def __init__(
        self, *, model: str = EMBEDDING_MODEL, dimension: int = EMBEDDING_DIMENSION
    ) -> None:
        self._model = model
        self._dimension = dimension
        self.calls: list[list[str]] = []

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        # A stable, per-text vector (first cell encodes the text length) so a test
        # can assert which text was embedded without a real model.
        return [[float(len(text))] + [0.0] * (self._dimension - 1) for text in texts]


class InMemoryEmbeddingRepository:
    """A dict-backed :class:`EmbeddingRepository` storing real ``Embedding`` rows."""

    def __init__(self) -> None:
        self._rows: dict[tuple[EmbedItemKind, int], Embedding] = {}

    async def get(self, kind: EmbedItemKind, item_id: int) -> Embedding | None:
        return self._rows.get((kind, item_id))

    async def upsert(
        self,
        *,
        user_id: int,
        kind: EmbedItemKind,
        item_id: int,
        content_hash: str,
        vector: list[float],
        model: str,
    ) -> None:
        self._rows[(kind, item_id)] = Embedding(
            item_kind=kind,
            item_id=item_id,
            user_id=user_id,
            content_hash=content_hash,
            vector=vector,
            model=model,
        )

    async def delete(self, kind: EmbedItemKind, item_id: int) -> None:
        self._rows.pop((kind, item_id), None)


class FakeEmbedQueue:
    """Records the embed/purge jobs the enqueue consumer would push."""

    def __init__(self) -> None:
        self.embeds: list[tuple[int, EmbedItemKind, int, str]] = []
        self.purges: list[tuple[int, EmbedItemKind, int]] = []

    async def enqueue_embed(
        self, user_id: int, kind: EmbedItemKind, item_id: int, content_hash: str
    ) -> None:
        self.embeds.append((user_id, kind, item_id, content_hash))

    async def enqueue_purge(self, user_id: int, kind: EmbedItemKind, item_id: int) -> None:
        self.purges.append((user_id, kind, item_id))


def corpus_item(text: str, content_hash: str, *, archived: bool = False) -> CorpusItem:
    """Build a :class:`CorpusItem` for seeding the fake resolver."""
    return CorpusItem(text=text, content_hash=content_hash, archived=archived)
