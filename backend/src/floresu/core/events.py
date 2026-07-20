"""The single write-event seam every content write publishes through.

Provenance is a differentiator, so every content write is attributed and recorded
through one seam rather than each service calling audit, SSE, and the embed queue
directly. A service commits its write and publishes exactly one :class:`WriteEvent`;
this seam fans it out to the registered consumers.

Consumers come in two kinds, distinguished by their failure contract:

- **Transactional consumers** run inside the write's own transaction, so they
  receive the caller's :class:`~sqlalchemy.ext.asyncio.AsyncSession` and enlist in
  it. Their failure propagates, so the ``transaction`` context the service wraps
  its write in rolls the whole write back. The audit append is the one
  transactional consumer, so a committed content write can never lack its audit
  row and a failed audit append is not silently dropped.
- **Best-effort consumers** are side channels (the SSE publish and the embed
  enqueue land here in later slices). Their failure is swallowed and logged, so a
  down side channel never fails the user's write. They currently run while the
  caller's transaction is still open (see :meth:`WriteEventPublisher.publish`), so
  a channel that must never emit for a write that later rolls back needs a
  post-commit dispatch, not just registration here.

The consumer lists are injected at the composition root, so a new side channel is
added there without editing this seam or any service.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from floresu.core.actor import Actor
from floresu.core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_log = get_logger("floresu-events")


class Action(StrEnum):
    """The closed set of content-write actions an audit row records.

    Every domain service publishes one of these; the set is closed so the audit
    log, activity feed, and item history share one vocabulary rather than each
    domain inventing free-text verbs.
    """

    CREATE = "create"
    UPDATE = "update"
    ARCHIVE = "archive"
    RESTORE = "restore"
    DELETE = "delete"
    FINALIZE = "finalize"
    PROMOTE = "promote"
    REORDER = "reorder"
    RENDER = "render"
    TAG = "tag"


class WriteEvent(BaseModel):
    """One content write, carrying who did it and what changed.

    ``user_id`` is the account the write belongs to (the audit row's owner and the
    SSE channel key); ``actor`` is the provenance descriptor (human vs named agent)
    resolved at the trust boundary. No field-level diff is carried: ``action`` plus
    an optional human ``summary`` and light structured ``metadata`` (scope,
    revision, template) is the whole record. Frozen so a published event cannot be
    mutated as it fans out to consumers.
    """

    model_config = ConfigDict(frozen=True)

    user_id: int
    actor: Actor
    entity_type: str
    entity_id: int
    action: Action
    summary: str | None = None
    metadata: dict[str, Any] | None = None


# A transactional consumer enlists in the write's transaction via the shared
# session, so its failure rolls the content write back. A best-effort consumer is
# a side channel whose failure never fails the write.
TransactionalConsumer = Callable[["AsyncSession", "WriteEvent"], Awaitable[None]]
BestEffortConsumer = Callable[["WriteEvent"], Awaitable[None]]


class WriteEventPublisher:
    """Fans one :class:`WriteEvent` out to its registered consumers.

    A singleton composed once at the composition root with the consumers each app
    wires. ``publish`` is called by a service from inside its ``transaction``
    block, right after the content write, so the transactional consumers commit or
    roll back atomically with the write.
    """

    def __init__(
        self,
        *,
        transactional: Sequence[TransactionalConsumer] = (),
        best_effort: Sequence[BestEffortConsumer] = (),
    ) -> None:
        self._transactional = tuple(transactional)
        self._best_effort = tuple(best_effort)

    async def publish(self, session: AsyncSession, event: WriteEvent) -> None:
        """Run the transactional consumers, then the best-effort side channels.

        Transactional consumers run first and are not guarded: a failure
        propagates so the caller's transaction rolls the content write back.
        Best-effort consumers run next; each is isolated so a failing side channel
        neither fails the write nor stops the other side channels.

        Timing constraint: this runs while the caller's transaction is still open
        (a service publishes from inside its ``transaction`` block so the audit
        append can roll the write back), so best-effort consumers observe a
        not-yet-committed write. A side channel that must never emit for a write
        that later rolls back (a live-feed publish, a queue enqueue) therefore
        needs to fire *after* commit: adding it to ``best_effort`` alone gives it
        the wrong timing and requires a seam change to defer it past commit.
        """
        for consumer in self._transactional:
            await consumer(session, event)
        for side_channel in self._best_effort:
            await self._run_best_effort(side_channel, event)

    async def _run_best_effort(self, consumer: BestEffortConsumer, event: WriteEvent) -> None:
        try:
            await consumer(event)
        except Exception as exc:  # a side channel is best-effort; never fail the write
            _log.warning(
                "write_event_side_channel_failed",
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                action=event.action.value,
                error=str(exc),
            )
