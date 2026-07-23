"""The embed-enqueue seam: map a committed write to an embed queue operation.

A content write publishes exactly one :class:`WriteEvent` through the write-event
seam; this module registers the post-commit consumer that turns that event into an
embed-pipeline operation. It runs post-commit (never inside the write's
transaction), so a rolled-back write never enqueues or embeds a phantom item, and
its failure never fails the (already committed) write.

:func:`embed_intent` is the pure policy: for an embeddable kind, a write carrying a
new content hash means re-embed; an archive means purge the vector; anything else
(an edges-only edit, a restore, a non-corpus kind) is ignored. Two consumers act
on that intent:

- :func:`build_async_embed_enqueue_consumer` (the external/web app) enqueues an arq
  job the worker drains: the default asynchronous path.
- :func:`build_sync_embed_fastpath_consumer` (the internal/agent app) runs the
  embed inline in a fresh transaction, so a write-then-search in the same agent
  turn sees the semantic vector without waiting on the worker.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from floresu.core.events import REEMBED_CONTENT_HASH_KEY, Action
from floresu.embedding.config import EmbedItemKind
from floresu.embedding.repository import SqlAlchemyEmbeddingRepository
from floresu.embedding.service import EmbeddingService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from floresu.core.events import PostCommitConsumer, RecordedWrite, WriteEvent
    from floresu.embedding.corpus import CorpusResolver
    from floresu.embedding.provider import EmbeddingProvider
    from floresu.embedding.queue import EmbedJobQueue

# The corpus kinds; a write for any other entity type is not embeddable.
_EMBEDDABLE_ENTITY_TYPES = frozenset(kind.value for kind in EmbedItemKind)


@dataclass(frozen=True)
class EmbedIntent:
    """A committed content change: (re)embed this item, gated by ``content_hash``."""

    user_id: int
    kind: EmbedItemKind
    item_id: int
    content_hash: str


@dataclass(frozen=True)
class PurgeIntent:
    """A committed archive: remove this item's vector so it never appears in results."""

    user_id: int
    kind: EmbedItemKind
    item_id: int


def embed_intent(event: WriteEvent) -> EmbedIntent | PurgeIntent | None:
    """Map a write event to an embed-pipeline intent, or ``None`` to ignore it.

    A content-changing write carries the new hash under ``REEMBED_CONTENT_HASH_KEY``
    (create + text edit); an edges-only edit omits it. An archive carries no hash
    but must purge the vector. A non-corpus entity type (a skill, an identity
    variant, a resume) is never embedded.
    """
    if event.entity_type not in _EMBEDDABLE_ENTITY_TYPES:
        return None
    kind = EmbedItemKind(event.entity_type)
    if event.action is Action.ARCHIVE:
        return PurgeIntent(user_id=event.user_id, kind=kind, item_id=event.entity_id)
    content_hash = (event.metadata or {}).get(REEMBED_CONTENT_HASH_KEY)
    if isinstance(content_hash, str):
        return EmbedIntent(
            user_id=event.user_id, kind=kind, item_id=event.entity_id, content_hash=content_hash
        )
    return None


def build_async_embed_enqueue_consumer(queue: EmbedJobQueue) -> PostCommitConsumer:
    """The default path: enqueue one embed/purge job per qualifying write."""

    async def consume(recorded: RecordedWrite) -> None:
        intent = embed_intent(recorded.event)
        if isinstance(intent, EmbedIntent):
            await queue.enqueue_embed(
                intent.user_id, intent.kind, intent.item_id, intent.content_hash
            )
        elif isinstance(intent, PurgeIntent):
            await queue.enqueue_purge(intent.user_id, intent.kind, intent.item_id)

    return consume


def build_sync_embed_fastpath_consumer(
    sessionmaker: async_sessionmaker[AsyncSession],
    resolver: CorpusResolver,
    provider: EmbeddingProvider,
) -> PostCommitConsumer:
    """The agent path: embed (or purge) the item inline so a same-turn search sees it.

    Runs in its own fresh session and transaction (the write's session has already
    committed), bounded to the one item the write touched.
    """

    async def consume(recorded: RecordedWrite) -> None:
        intent = embed_intent(recorded.event)
        if intent is None:
            return
        async with sessionmaker() as session:
            service = EmbeddingService(
                session, SqlAlchemyEmbeddingRepository(session), resolver, provider
            )
            if isinstance(intent, EmbedIntent):
                await service.embed_item(
                    str(intent.user_id), intent.kind, intent.item_id, intent.content_hash
                )
            else:
                await service.delete_vector(str(intent.user_id), intent.kind, intent.item_id)

    return consume
