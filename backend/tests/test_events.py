"""The write-event seam (:class:`WriteEventPublisher`).

Drives the real publisher with recording consumers and a fake session (the seam
passes the session through to transactional consumers and uses ``session.info`` to
defer post-commit side channels). Covers the failure and timing contract that is
the whole point of the seam: a failing transactional consumer propagates so the
caller's transaction rolls the write back, while post-commit side channels are
deferred onto the session's queue (never run inline) so they only fire once the
write commits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest

from floresu.core.events import RecordedWrite, WriteEventPublisher
from floresu.core.post_commit import run_post_commit
from tests.audit_fakes import build_recorded_write, build_write_event

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.events import PostCommitConsumer, TransactionalConsumer, WriteEvent


class _FakeSession:
    """The seam only reads ``session.info`` (to defer post-commit tasks) and hands
    the session to transactional consumers, so a bare object with an ``info`` dict
    is a faithful stand-in for the unit-level seam tests."""

    def __init__(self) -> None:
        self.info: dict[str, Any] = {}


def _as_session(fake: _FakeSession) -> AsyncSession:
    return cast("AsyncSession", fake)


class _Recorder:
    """Records the order of consumer invocations across both kinds."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.sessions: list[AsyncSession] = []
        self.recorded: list[RecordedWrite] = []

    def transactional(
        self, name: str, *, records: RecordedWrite | None = None
    ) -> TransactionalConsumer:
        async def consume(session: AsyncSession, event: WriteEvent) -> RecordedWrite | None:
            self.calls.append(name)
            self.sessions.append(session)
            return records

        return consume

    def post_commit(self, name: str) -> PostCommitConsumer:
        async def consume(recorded: RecordedWrite) -> None:
            self.calls.append(name)
            self.recorded.append(recorded)

        return consume


async def test_publish_runs_transactional_consumers_and_defers_post_commit() -> None:
    recorder = _Recorder()
    recorded = build_recorded_write()
    session = _FakeSession()
    publisher = WriteEventPublisher(
        transactional=[recorder.transactional("audit", records=recorded)],
        post_commit=[recorder.post_commit("sse"), recorder.post_commit("embed")],
    )

    await publisher.publish(_as_session(session), recorded.event)

    # The transactional consumer ran and received the session; the post-commit side
    # channels are deferred (enqueued), not run inline.
    assert recorder.calls == ["audit"]
    assert recorder.sessions == [_as_session(session)]

    # Draining the session queue (what the transaction boundary does post-commit)
    # runs the side channels, each with the recorded write.
    await run_post_commit(_as_session(session))
    assert recorder.calls == ["audit", "sse", "embed"]
    assert recorder.recorded == [recorded, recorded]


async def test_a_failing_transactional_consumer_propagates_and_defers_nothing() -> None:
    recorder = _Recorder()
    session = _FakeSession()

    async def failing(_session: AsyncSession, _event: WriteEvent) -> RecordedWrite | None:
        raise RuntimeError("audit append failed")

    publisher = WriteEventPublisher(
        transactional=[failing],
        post_commit=[recorder.post_commit("sse")],
    )

    with pytest.raises(RuntimeError, match="audit append failed"):
        await publisher.publish(_as_session(session), build_write_event())
    # The write rolls back, so nothing is deferred and no side channel can run.
    assert session.info == {}
    await run_post_commit(_as_session(session))
    assert recorder.calls == []


async def test_post_commit_is_skipped_when_no_write_was_recorded() -> None:
    recorder = _Recorder()
    session = _FakeSession()
    publisher = WriteEventPublisher(
        # A transactional consumer that records nothing (returns None).
        transactional=[recorder.transactional("noop", records=None)],
        post_commit=[recorder.post_commit("sse")],
    )

    await publisher.publish(_as_session(session), build_write_event())

    # With no durable id to publish, the side channel is not enqueued.
    assert recorder.calls == ["noop"]
    await run_post_commit(_as_session(session))
    assert recorder.calls == ["noop"]


async def test_publish_with_no_consumers_is_a_noop() -> None:
    session = _FakeSession()
    await WriteEventPublisher().publish(_as_session(session), build_write_event())
    assert session.info == {}
