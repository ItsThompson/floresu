"""The single write-event seam every content write publishes through.

Provenance is a differentiator, so every content write is attributed and recorded
through one seam rather than each service calling audit, SSE, and the embed queue
directly. A service commits its write and publishes exactly one :class:`WriteEvent`;
this seam fans it out to the registered consumers.

Consumers come in two kinds, distinguished by when they run and their failure
contract:

- **Transactional consumers** run inside the write's own transaction, so they
  receive the caller's :class:`~sqlalchemy.ext.asyncio.AsyncSession` and enlist in
  it. Their failure propagates, so the ``transaction`` context the service wraps
  its write in rolls the whole write back. The audit append is the one
  transactional consumer, so a committed content write can never lack its audit
  row and a failed audit append is not silently dropped. It mints the monotonic
  ``audit_log.id`` and returns a :class:`RecordedWrite` carrying it.
- **Post-commit consumers** are side channels (the SSE publish; the embed enqueue).
  They must not emit for a write that later rolls back, so they do not run inline:
  :meth:`WriteEventPublisher.publish` enqueues them on the
  session's post-commit queue (:mod:`floresu.core.post_commit`), and the
  ``transaction`` boundary runs them only after a successful commit. Each runs
  isolated, so a down side channel never fails the (already committed) write. They
  receive the :class:`RecordedWrite`, so an SSE frame can carry the real event id.

The consumer lists are injected at the composition root, so a new side channel is
added there without editing this seam or any service.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from floresu.core.actor import Actor
from floresu.core.logging import get_logger
from floresu.core.post_commit import enqueue_post_commit

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from starlette.applications import Starlette

_log = get_logger("floresu-events")

# The write-event ``metadata`` key that carries the re-embed trigger. A write that
# warrants (re)embedding (a create, or an edit that changes the content hash)
# carries the new content hash under this key; the embed consumer (a post-commit
# side channel) keys on its presence and compares the hash to gate embedding. An
# edit that leaves the hash unchanged omits it, so no
# re-embed is signalled. It is the shared writer-to-embed-consumer contract, so it
# lives with the write-event contract rather than in one domain: worklog and
# bullets publish it today, and any other embeddable domain uses this same key.
REEMBED_CONTENT_HASH_KEY = "content_hash"

# The write-event ``metadata`` key that carries the copy-on-write scope of a
# bulletpoint edit (``this_resume`` | ``everywhere``). Recorded on the audit row so
# per-item history and the activity feed can show an edit's blast radius. Like the
# re-embed key it is a cross-domain audit-metadata contract, so it lives with the
# write-event contract rather than in the resume or library domain.
SCOPE_METADATA_KEY = "scope"


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


class RecordedWrite(BaseModel):
    """A :class:`WriteEvent` after the audit log has recorded it.

    Carries the source ``event`` plus the monotonic ``audit_id`` (the SSE event id
    and the feed's ordering key) and the ``created_at`` the audit row was stamped
    with. This is what post-commit side channels receive, so an SSE frame carries
    the durable record's real id rather than a fabricated one. Frozen for the same
    reason as :class:`WriteEvent`.
    """

    model_config = ConfigDict(frozen=True)

    event: WriteEvent
    audit_id: int
    created_at: datetime


# A transactional consumer enlists in the write's transaction via the shared
# session, so its failure rolls the content write back. The audit consumer returns
# the :class:`RecordedWrite` it minted; a consumer with nothing to record returns
# ``None``. A post-commit consumer is a side channel that runs after the commit and
# whose failure never fails the write.
TransactionalConsumer = Callable[["AsyncSession", "WriteEvent"], Awaitable["RecordedWrite | None"]]
PostCommitConsumer = Callable[["RecordedWrite"], Awaitable[None]]


class WriteEventPublisher:
    """Fans one :class:`WriteEvent` out to its registered consumers.

    A singleton composed once at the composition root with the consumers each app
    wires. ``publish`` is called by a service from inside its ``transaction``
    block, right after the content write, so the transactional consumers commit or
    roll back atomically with the write and the post-commit side channels are
    deferred until that transaction commits.
    """

    def __init__(
        self,
        *,
        transactional: Sequence[TransactionalConsumer] = (),
        post_commit: Sequence[PostCommitConsumer] = (),
    ) -> None:
        self._transactional = tuple(transactional)
        self._post_commit = tuple(post_commit)

    async def publish(self, session: AsyncSession, event: WriteEvent) -> None:
        """Run the transactional consumers, then defer the post-commit side channels.

        Transactional consumers run first and are not guarded: a failure propagates
        so the caller's transaction rolls the content write back. The audit append
        returns the :class:`RecordedWrite` it minted (the event plus its durable
        ``audit_id``).

        The post-commit consumers are not run here: they are enqueued on the
        session's post-commit queue, which :func:`floresu.core.db.transaction`
        drains only after a successful commit. A write that rolls back therefore
        emits nothing on the side channels (no phantom SSE event, no stray enqueue),
        and each side channel runs isolated after commit.
        """
        recorded: RecordedWrite | None = None
        for consumer in self._transactional:
            result = await consumer(session, event)
            if result is not None:
                recorded = result
        if not self._post_commit:
            return
        if recorded is None:
            # No transactional consumer recorded the write, so there is no durable
            # id to publish. Skip rather than emit a side-channel event with none.
            _log.warning(
                "post_commit_skipped_unrecorded_write",
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                action=event.action.value,
            )
            return
        for side_channel in self._post_commit:
            enqueue_post_commit(session, _bind(side_channel, recorded))


def _bind(consumer: PostCommitConsumer, recorded: RecordedWrite) -> Callable[[], Awaitable[None]]:
    """Bind a post-commit consumer to its recorded write as a no-arg coroutine.

    A named factory (not an inline lambda in the loop) so each enqueued task
    captures its own ``consumer``, never the loop variable's final value.
    """

    async def task() -> None:
        await consumer(recorded)

    return task


# The ``app.state`` attribute the write-event seam is set on and read from.
EVENTS_ATTR = "events"


def get_events(app: Starlette) -> WriteEventPublisher:
    """The injected write-event publisher.

    Unlike :func:`~floresu.core.identity.get_session_verifier`'s deny-all default,
    this fails loud when the seam is unset or the wrong type: a missing publisher
    would silently drop the audit/feed/embed fan-out, which is worse than a
    startup-time failure. Both composition roots set ``app.state.events``, so an
    unset seam is a wiring bug. Starlette's ``app.state`` launders to ``Any``, so
    this typed accessor is the one place the seam is read.
    """
    publisher = getattr(app.state, EVENTS_ATTR, None)
    if not isinstance(publisher, WriteEventPublisher):
        raise RuntimeError("app.state.events is not wired to a WriteEventPublisher.")
    return publisher


async def emit_write_event(
    publisher: WriteEventPublisher,
    session: AsyncSession,
    *,
    user_id: int,
    actor: Actor,
    entity_type: str,
    entity_id: int,
    action: Action,
    summary: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Build one :class:`WriteEvent`, publish it through the seam, and log the publish.

    The single construction site for a :class:`WriteEvent`. Per-domain ``_publish``
    wrappers bind their own ``entity_type``/``action`` and delegate here; the
    divergent sites (render, lifecycle, finalize) pass their own
    ``entity_type``/``action``/``metadata`` as arguments, so there is no second
    code path.

    The publish log fires here, inside the caller's ``transaction`` block before
    commit. A later rollback still leaves this line emitted (the intent to publish
    is real; the post-commit fan-out is deferred to commit), matching the
    warning-on-skip behavior in :meth:`WriteEventPublisher.publish`.
    """
    event = WriteEvent(
        user_id=user_id,
        actor=actor,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        summary=summary,
        metadata=metadata,
    )
    await publisher.publish(session, event)
    _log.info(
        "write_event_published",
        entity_type=entity_type,
        entity_id=entity_id,
        action=action.value,
    )
