"""The Redis-backed feed store: publish, replay, and live subscription.

Wraps the async Redis client with the three operations the live activity feed
needs, so the SSE endpoint and the write-event side channel never touch Redis
directly:

- :meth:`publish` appends one event to the user's bounded replay buffer and
  publishes it on the user's channel (buffer first, so a client that reconnects
  just after the live publish can still replay it).
- :meth:`replay_since` returns the gap: buffered events with an id greater than the
  client's ``Last-Event-ID``, in ascending id order.
- :meth:`listen` yields live events for a user, emitting ``None`` on each idle
  timeout so the stream can send a heartbeat, and cleaning up its subscription on
  exit.

Events cross Redis as the :class:`~floresu.audit.schemas.AuditEntry` JSON, the same
shape the initial page load and the frontend dedup use, so the id semantics are
identical on both paths.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.audit.schemas import AuditEntry
from floresu.feed.channels import replay_key, user_channel
from floresu.feed.config import REPLAY_BUFFER_SIZE

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from redis.asyncio import Redis


class RedisFeedStore:
    """Per-user pub/sub fan-out plus a bounded replay buffer over Redis."""

    def __init__(self, redis: Redis, *, buffer_size: int = REPLAY_BUFFER_SIZE) -> None:
        self._redis = redis
        self._buffer_size = buffer_size

    async def publish(self, user_id: int, entry: AuditEntry) -> None:
        """Buffer then publish one event for ``user_id``.

        The buffer add, the trim to the last ``buffer_size`` events, and the channel
        publish run in one pipeline. The buffer add precedes the publish so a client
        reconnecting between the two still finds the event in the replay buffer.
        """
        payload = entry.model_dump_json()
        key = replay_key(user_id)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.zadd(key, {payload: entry.id})
            # Keep only the highest-scored (newest-id) buffer_size members.
            pipe.zremrangebyrank(key, 0, -(self._buffer_size + 1))
            pipe.publish(user_channel(user_id), payload)
            await pipe.execute()

    async def replay_since(self, user_id: int, last_event_id: int) -> list[AuditEntry]:
        """Buffered events with id greater than ``last_event_id``, oldest-first."""
        raw = await self._redis.zrangebyscore(
            replay_key(user_id), min=f"({last_event_id}", max="+inf"
        )
        return [AuditEntry.model_validate_json(item) for item in raw]

    async def listen(
        self, user_id: int, *, heartbeat_timeout: float
    ) -> AsyncGenerator[AuditEntry | None, None]:
        """Yield live events for ``user_id``; yield ``None`` on each idle timeout.

        The idle ``None`` lets the caller emit a heartbeat frame. The subscription
        is torn down on exit (client disconnect closes the consuming generator,
        which propagates here).
        """
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(user_channel(user_id))
        try:
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=heartbeat_timeout
                )
                if message is None:
                    yield None
                    continue
                yield AuditEntry.model_validate_json(message["data"])
        finally:
            await pubsub.unsubscribe(user_channel(user_id))
            # PubSub.aclose ships without a return annotation in redis-py.
            await pubsub.aclose()  # type: ignore[no-untyped-call]
