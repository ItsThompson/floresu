"""SSE frame formatting for the activity feed stream.

Turns the feed store's event flow into a ``text/event-stream`` body: an optional
gap replay first (buffered events with id greater than the client's
``Last-Event-ID``), then the live events, with a comment heartbeat frame on each
idle tick. Each event frame carries the monotonic ``audit_log.id`` as the SSE
``id:`` field, so the browser's ``EventSource`` reports it back as
``Last-Event-ID`` on reconnect and the client dedups against it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.feed.config import HEARTBEAT_INTERVAL_SECONDS

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from floresu.audit.schemas import AuditEntry
    from floresu.feed.store import RedisFeedStore

# A comment frame (starts with ':'), ignored by EventSource but enough traffic to
# stop the tunnel/edge idle-buffering or closing the stream between events.
HEARTBEAT_FRAME = ": keepalive\n\n"


def event_frame(entry: AuditEntry) -> str:
    """Format one audit entry as an SSE event frame with its id as the event id."""
    return f"id: {entry.id}\ndata: {entry.model_dump_json()}\n\n"


async def feed_frames(
    store: RedisFeedStore,
    user_id: int,
    last_event_id: int | None,
    *,
    heartbeat_timeout: float = HEARTBEAT_INTERVAL_SECONDS,
) -> AsyncIterator[str]:
    """The SSE body for one feed connection: gap replay, then live events.

    On reconnect (``last_event_id`` set) the buffered gap is replayed in order
    before live streaming resumes. A replayed event may also arrive live; the
    client dedups by id, so the overlap is harmless.
    """
    if last_event_id is not None:
        for buffered in await store.replay_since(user_id, last_event_id):
            yield event_frame(buffered)
    async for live in store.listen(user_id, heartbeat_timeout=heartbeat_timeout):
        yield HEARTBEAT_FRAME if live is None else event_frame(live)
