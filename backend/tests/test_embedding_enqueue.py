"""Unit tests for the embed-enqueue seam: the intent policy and the async consumer.

``embed_intent`` is pure, so it is tested directly across content edits, archives,
edges-only edits, restores, and non-corpus kinds. The async enqueue consumer runs
over a recording queue. The synchronous fast-path consumer needs a real repository
and is covered end-to-end in the integration tests.
"""

from __future__ import annotations

from datetime import UTC, datetime

from floresu.core.actor import Actor, ActorType
from floresu.core.events import REEMBED_CONTENT_HASH_KEY, Action, RecordedWrite, WriteEvent
from floresu.embedding.config import EmbedItemKind
from floresu.embedding.enqueue import (
    EmbedIntent,
    PurgeIntent,
    build_async_embed_enqueue_consumer,
    embed_intent,
)
from tests.embedding_fakes import FakeEmbedQueue

_HUMAN = Actor(type=ActorType.HUMAN)


def _event(
    *,
    entity_type: str = "worklog",
    entity_id: int = 5,
    action: Action = Action.CREATE,
    metadata: dict[str, object] | None = None,
    user_id: int = 1,
) -> WriteEvent:
    return WriteEvent(
        user_id=user_id,
        actor=_HUMAN,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        summary=None,
        metadata=metadata,
    )


def _recorded(event: WriteEvent) -> RecordedWrite:
    return RecordedWrite(event=event, audit_id=1, created_at=datetime.now(UTC))


def test_intent_content_change_yields_embed() -> None:
    event = _event(action=Action.CREATE, metadata={REEMBED_CONTENT_HASH_KEY: "h1"})
    intent = embed_intent(event)
    assert intent == EmbedIntent(
        user_id=1, kind=EmbedItemKind.WORKLOG, item_id=5, content_hash="h1"
    )


def test_intent_edges_only_edit_yields_nothing() -> None:
    # An update with no content-hash key in metadata is an edges/tags/date edit.
    assert embed_intent(_event(action=Action.UPDATE, metadata=None)) is None
    assert embed_intent(_event(action=Action.UPDATE, metadata={"scope": "this"})) is None


def test_intent_archive_yields_purge() -> None:
    intent = embed_intent(_event(entity_type="bullet", entity_id=9, action=Action.ARCHIVE))
    assert intent == PurgeIntent(user_id=1, kind=EmbedItemKind.BULLET, item_id=9)


def test_intent_restore_yields_nothing() -> None:
    # A restore carries no content hash; the item re-embeds on its next edit.
    assert embed_intent(_event(action=Action.RESTORE, metadata=None)) is None


def test_intent_ignores_non_corpus_kinds() -> None:
    assert (
        embed_intent(_event(entity_type="skill", metadata={REEMBED_CONTENT_HASH_KEY: "h"})) is None
    )
    assert embed_intent(_event(entity_type="identity_variant", action=Action.ARCHIVE)) is None
    assert embed_intent(_event(entity_type="resume", action=Action.ARCHIVE)) is None


def test_intent_covers_source_kind() -> None:
    intent = embed_intent(
        _event(entity_type="source", entity_id=3, metadata={REEMBED_CONTENT_HASH_KEY: "hs"})
    )
    assert intent == EmbedIntent(user_id=1, kind=EmbedItemKind.SOURCE, item_id=3, content_hash="hs")


async def test_async_consumer_enqueues_one_embed_on_content_change() -> None:
    queue = FakeEmbedQueue()
    consume = build_async_embed_enqueue_consumer(queue)

    await consume(_recorded(_event(metadata={REEMBED_CONTENT_HASH_KEY: "h1"})))

    assert queue.embeds == [(1, EmbedItemKind.WORKLOG, 5, "h1")]
    assert queue.purges == []


async def test_async_consumer_enqueues_nothing_on_unchanged_hash() -> None:
    queue = FakeEmbedQueue()
    consume = build_async_embed_enqueue_consumer(queue)

    await consume(_recorded(_event(action=Action.UPDATE, metadata=None)))

    assert queue.embeds == []
    assert queue.purges == []


async def test_async_consumer_enqueues_purge_on_archive() -> None:
    queue = FakeEmbedQueue()
    consume = build_async_embed_enqueue_consumer(queue)

    await consume(_recorded(_event(entity_type="source", entity_id=7, action=Action.ARCHIVE)))

    assert queue.purges == [(1, EmbedItemKind.SOURCE, 7)]
    assert queue.embeds == []
