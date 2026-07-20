"""Compose the activity-feed side channel and its request-time dependencies.

Two seams live here, both kept out of the router and the entrypoint:

- :func:`build_sse_feed_consumer` builds the post-commit consumer the write-event
  seam fans out to. It maps the recorded write to the wire :class:`AuditEntry` and
  publishes it to the user's Redis channel + replay buffer. Registered at the
  composition root as a ``post_commit`` consumer, so it fires only after the write
  commits and its failure never fails the write.
- :func:`get_feed_store` resolves the process-wide :class:`RedisFeedStore` the SSE
  endpoint streams from, off ``app.state`` (attached at wiring time), mirroring how
  the DB layer resolves ``app.state.db``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from starlette.requests import Request

from floresu.audit.schemas import AuditEntry
from floresu.feed.store import RedisFeedStore

if TYPE_CHECKING:
    from floresu.core.events import PostCommitConsumer, RecordedWrite

# The ``app.state`` attribute the SSE endpoint resolves the feed store from.
FEED_STORE_ATTR = "feed_store"


def build_sse_feed_consumer(store: RedisFeedStore) -> PostCommitConsumer:
    """The post-commit side channel that publishes a recorded write to the feed."""

    async def consume(recorded: RecordedWrite) -> None:
        await store.publish(recorded.event.user_id, _entry_from_recorded(recorded))

    return consume


def _entry_from_recorded(recorded: RecordedWrite) -> AuditEntry:
    """Project a recorded write onto the audit-entry wire shape the feed streams.

    The same shape the initial page load and item history return, so the frontend
    dedups the live event against the initial rows by a single ``id``.
    """
    event = recorded.event
    return AuditEntry(
        id=recorded.audit_id,
        actor_type=event.actor.type,
        actor_label=event.actor.label,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        action=event.action.value,
        summary=event.summary,
        metadata=event.metadata,
        created_at=recorded.created_at,
    )


def get_feed_store(request: Request) -> RedisFeedStore:
    """FastAPI dependency resolving the process-wide feed store off ``app.state``."""
    return cast("RedisFeedStore", getattr(request.app.state, FEED_STORE_ATTR))
