"""The write-event seam (:class:`WriteEventPublisher`).

Drives the real publisher with recording consumers and a sentinel session (the
seam only passes the session through to transactional consumers, never touches
it). Covers the failure contract that is the whole point of the seam: a failing
transactional consumer propagates so the caller's transaction rolls the write
back, while a failing best-effort side channel is swallowed and never stops the
write or the other side channels.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from floresu.core.events import WriteEventPublisher
from tests.audit_fakes import build_write_event

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.events import BestEffortConsumer, TransactionalConsumer, WriteEvent

# The seam passes this straight to transactional consumers without using it.
SESSION = cast("AsyncSession", object())


class _Recorder:
    """Records the order of consumer invocations across both kinds."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.sessions: list[AsyncSession] = []
        self.events: list[WriteEvent] = []

    def transactional(self, name: str) -> TransactionalConsumer:
        async def consume(session: AsyncSession, event: WriteEvent) -> None:
            self.calls.append(name)
            self.sessions.append(session)
            self.events.append(event)

        return consume

    def best_effort(self, name: str) -> BestEffortConsumer:
        async def consume(event: WriteEvent) -> None:
            self.calls.append(name)
            self.events.append(event)

        return consume


async def test_publish_fans_out_to_every_consumer() -> None:
    recorder = _Recorder()
    publisher = WriteEventPublisher(
        transactional=[recorder.transactional("audit")],
        best_effort=[recorder.best_effort("sse"), recorder.best_effort("embed")],
    )
    event = build_write_event()

    await publisher.publish(SESSION, event)

    assert recorder.calls == ["audit", "sse", "embed"]
    # Transactional consumers receive the caller's session; best-effort ones do not.
    assert recorder.sessions == [SESSION]
    assert all(seen is event for seen in recorder.events)


async def test_a_failing_transactional_consumer_propagates() -> None:
    recorder = _Recorder()

    async def failing(_session: AsyncSession, _event: WriteEvent) -> None:
        raise RuntimeError("audit append failed")

    publisher = WriteEventPublisher(
        transactional=[failing],
        best_effort=[recorder.best_effort("sse")],
    )

    with pytest.raises(RuntimeError, match="audit append failed"):
        await publisher.publish(SESSION, build_write_event())
    # The write must roll back, so the best-effort side channels never run.
    assert recorder.calls == []


async def test_a_failing_best_effort_consumer_is_swallowed() -> None:
    recorder = _Recorder()

    async def failing(_event: WriteEvent) -> None:
        raise RuntimeError("sse publish failed")

    publisher = WriteEventPublisher(
        transactional=[recorder.transactional("audit")],
        best_effort=[failing, recorder.best_effort("embed")],
    )

    # publish returns normally: a down side channel never fails the write.
    await publisher.publish(SESSION, build_write_event())
    # The transactional consumer ran and the sibling side channel still ran.
    assert recorder.calls == ["audit", "embed"]


async def test_publish_with_no_consumers_is_a_noop() -> None:
    await WriteEventPublisher().publish(SESSION, build_write_event())
