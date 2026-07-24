"""Deferred post-commit side effects, queued on the write session.

A side channel that must not emit for a write that later rolls back (the SSE feed
publish, the embed enqueue) cannot run inside the write's transaction: it would
observe a not-yet-committed write and fire even if the write rolls back. The
write-event seam enqueues such work here, keyed on the caller's session, and the
transaction boundary (:func:`floresu.core.db.transaction`) drains it only after a
successful commit. A rolled-back write clears the queue and emits nothing.

The tasks are best-effort: each runs isolated so a down side channel neither fails
the (already committed) write nor stops the sibling side channels.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

_log = get_logger("floresu-events")

# The ``session.info`` key the deferred task list lives under. Session-scoped so
# concurrent requests (each with its own session) never share a queue.
_QUEUE_KEY = "floresu_post_commit"


def enqueue_post_commit(session: AsyncSession, task: Callable[[], Awaitable[None]]) -> None:
    """Queue a task to run after the caller's transaction commits."""
    queue: list[Callable[[], Awaitable[None]]] = session.info.setdefault(_QUEUE_KEY, [])
    queue.append(task)


def discard_post_commit(session: AsyncSession) -> None:
    """Drop any queued tasks without running them (the transaction rolled back)."""
    session.info.pop(_QUEUE_KEY, None)


async def run_post_commit(session: AsyncSession) -> None:
    """Run and clear the queued tasks after a successful commit.

    Each task is isolated: a failure is swallowed and logged so a down side channel
    never propagates out of the (already committed) write.
    """
    tasks: list[Callable[[], Awaitable[None]]] = session.info.pop(_QUEUE_KEY, [])
    for task in tasks:
        try:
            await task()
        except Exception:  # a post-commit side channel is best-effort
            _log.warning("post_commit_task_failed", exc_info=True)
