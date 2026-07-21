"""The embed job queue: the narrow interface the enqueue seam depends on.

The external app enqueues one job per content-changing (or archiving) write onto
the arq queue the worker drains. The seam depends on the small
:class:`EmbedJobQueue` interface, not on arq, so the post-commit consumer is
testable with a recording fake and no broker.

:class:`ArqEmbedQueue` is the P0 implementation over an ``ArqRedis`` pool bound at
the composition root. The pool connects lazily (like the shared Redis client), so
building the app needs no reachable broker; a broker outage degrades the
best-effort enqueue (the write already committed) rather than failing the write.
"""

from __future__ import annotations

from typing import Protocol, cast, runtime_checkable

from arq.connections import ArqRedis

from floresu.embedding.config import (
    EMBED_ITEM_JOB,
    EMBED_QUEUE_NAME,
    PURGE_ITEM_JOB,
    EmbedItemKind,
)


@runtime_checkable
class EmbedJobQueue(Protocol):
    """Enqueues the two embed jobs the worker runs, scoped to the item's owner."""

    async def enqueue_embed(
        self, user_id: int, kind: EmbedItemKind, item_id: int, content_hash: str
    ) -> None:
        """Enqueue a re-embed of one item, gated at run time by ``content_hash``."""
        ...

    async def enqueue_purge(self, user_id: int, kind: EmbedItemKind, item_id: int) -> None:
        """Enqueue removal of one item's vector (archived or deleted)."""
        ...


class ArqEmbedQueue:
    """Enqueues embed/purge jobs onto the arq queue the worker drains."""

    def __init__(self, pool: ArqRedis) -> None:
        self._pool = pool

    async def enqueue_embed(
        self, user_id: int, kind: EmbedItemKind, item_id: int, content_hash: str
    ) -> None:
        await self._pool.enqueue_job(
            EMBED_ITEM_JOB,
            user_id,
            kind.value,
            item_id,
            content_hash,
            _queue_name=EMBED_QUEUE_NAME,
        )

    async def enqueue_purge(self, user_id: int, kind: EmbedItemKind, item_id: int) -> None:
        await self._pool.enqueue_job(
            PURGE_ITEM_JOB,
            user_id,
            kind.value,
            item_id,
            _queue_name=EMBED_QUEUE_NAME,
        )

    async def aclose(self) -> None:
        """Close the underlying arq pool's connections on shutdown."""
        await self._pool.aclose()


def create_arq_pool(redis_url: str) -> ArqRedis:
    """Build the lazy-connecting arq pool the enqueue seam pushes jobs onto."""
    # ``from_url`` is inherited from redis-py (untyped), so it widens to ``Any``.
    return cast("ArqRedis", ArqRedis.from_url(redis_url))
