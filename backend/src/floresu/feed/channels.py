"""Redis key names for the per-user activity feed.

The feed fans out over two Redis structures keyed by the account id, defined here
once so the publisher, the replay reader, and the SSE subscription never re-derive
the format:

- a pub/sub channel ``feed:{user_id}`` carrying each event as it is written, and
- a bounded sorted-set replay buffer ``feed:replay:{user_id}`` scored by the
  monotonic ``audit_log.id``, which a reconnecting client replays the gap from.

The ``feed:{user_id}`` channel format is the provenance-spec contract (section 09).
"""

from __future__ import annotations


def user_channel(user_id: int) -> str:
    """The pub/sub channel every write for ``user_id`` is published to."""
    return f"feed:{user_id}"


def replay_key(user_id: int) -> str:
    """The bounded replay-buffer key for ``user_id`` (a sorted set scored by id)."""
    return f"feed:replay:{user_id}"
