"""End-to-end feed store tests against real Redis: publish, replay, and pub/sub.

Exercises :class:`RedisFeedStore` with a live Redis (via testcontainers): the
bounded replay buffer (trim + gap read) and the live pub/sub subscription with its
idle heartbeat tick. Skips automatically when Docker is unavailable.
"""

from __future__ import annotations

import asyncio

import pytest

from floresu.core.redis import create_redis_client
from floresu.feed.store import RedisFeedStore
from tests.audit_fakes import build_audit_entry

pytestmark = pytest.mark.integration


async def test_replay_since_returns_only_the_gap_in_order(redis_url: str) -> None:
    client = create_redis_client(redis_url)
    try:
        await client.flushdb()
        store = RedisFeedStore(client)
        for event_id in (1, 2, 3, 4):
            await store.publish(1, build_audit_entry(id=event_id, entity_id=event_id))

        gap = await store.replay_since(1, last_event_id=2)

        assert [entry.id for entry in gap] == [3, 4]
    finally:
        await client.aclose()


async def test_replay_buffer_is_bounded_to_the_newest_events(redis_url: str) -> None:
    client = create_redis_client(redis_url)
    try:
        await client.flushdb()
        store = RedisFeedStore(client, buffer_size=3)
        for event_id in (1, 2, 3, 4, 5):
            await store.publish(2, build_audit_entry(id=event_id, entity_id=event_id))

        # Only the newest 3 ids survive the trim; older ids are evicted.
        gap = await store.replay_since(2, last_event_id=0)

        assert [entry.id for entry in gap] == [3, 4, 5]
    finally:
        await client.aclose()


async def test_a_published_event_reaches_a_live_subscriber_after_a_heartbeat(
    redis_url: str,
) -> None:
    client = create_redis_client(redis_url)
    try:
        await client.flushdb()
        store = RedisFeedStore(client)
        stream = store.listen(3, heartbeat_timeout=0.2)

        # First poll: no event yet, so an idle heartbeat tick (None). This also
        # confirms the subscription is established before we publish.
        first = await stream.__anext__()
        assert first is None

        await store.publish(3, build_audit_entry(id=8, entity_id=8))
        live = await asyncio.wait_for(stream.__anext__(), timeout=2)

        assert live is not None
        assert live.id == 8
        await stream.aclose()
    finally:
        await client.aclose()
