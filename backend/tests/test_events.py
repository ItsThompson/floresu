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
import structlog
from starlette.applications import Starlette

from floresu.core.events import (
    Action,
    RecordedWrite,
    WriteEvent,
    WriteEventPublisher,
    emit_write_event,
    get_events,
)
from floresu.core.post_commit import run_post_commit
from tests.audit_fakes import build_recorded_write, build_write_event, human_actor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.events import PostCommitConsumer, TransactionalConsumer


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


async def _capture_emitted(**kwargs: Any) -> WriteEvent:
    """Run ``emit_write_event`` through a real publisher and return the built event.

    A recording transactional consumer captures exactly the :class:`WriteEvent`
    the emitter constructed and handed to the seam, so a shape test asserts against
    the real construction rather than a re-derived copy.
    """
    captured: list[WriteEvent] = []

    async def capture(_session: AsyncSession, event: WriteEvent) -> RecordedWrite | None:
        captured.append(event)
        return None

    publisher = WriteEventPublisher(transactional=[capture])
    await emit_write_event(publisher, _as_session(_FakeSession()), **kwargs)
    assert len(captured) == 1
    return captured[0]


async def test_emit_builds_the_event_publishes_it_and_logs_the_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[WriteEvent] = []

    async def capture(_session: AsyncSession, event: WriteEvent) -> RecordedWrite | None:
        captured.append(event)
        return None

    publisher = WriteEventPublisher(transactional=[capture])
    cap = structlog.testing.CapturingLogger()
    monkeypatch.setattr("floresu.core.events._log", cap)

    await emit_write_event(
        publisher,
        _as_session(_FakeSession()),
        user_id=7,
        actor=human_actor(),
        entity_type="worklog",
        entity_id=100,
        action=Action.CREATE,
        summary="Added an entry",
        metadata={"content_hash": "abc"},
    )

    # The seam received exactly the event the emitter constructed from its params.
    assert captured == [
        WriteEvent(
            user_id=7,
            actor=human_actor(),
            entity_type="worklog",
            entity_id=100,
            action=Action.CREATE,
            summary="Added an entry",
            metadata={"content_hash": "abc"},
        )
    ]
    # Exactly one publish log carrying entity_type, entity_id, and action.value.
    info_calls = [call for call in cap.calls if call.method_name == "info"]
    assert len(info_calls) == 1
    assert info_calls[0].args == ("write_event_published",)
    assert info_calls[0].kwargs == {
        "entity_type": "worklog",
        "entity_id": 100,
        "action": "create",
    }


async def test_emit_expresses_the_render_shape() -> None:
    # render: hardcoded Action.RENDER plus inline metadata.
    event = await _capture_emitted(
        user_id=1,
        actor=human_actor(),
        entity_type="resume",
        entity_id=55,
        action=Action.RENDER,
        summary="Exported resume",
        metadata={"template": "modern", "revision": 3},
    )
    assert event.action is Action.RENDER
    assert event.metadata == {"template": "modern", "revision": 3}


async def test_emit_expresses_the_lifecycle_shape() -> None:
    # lifecycle: parametrized entity_type, hardcoded Action.DELETE, permanent flag.
    event = await _capture_emitted(
        user_id=1,
        actor=human_actor(),
        entity_type="account",
        entity_id=1,
        action=Action.DELETE,
        summary="Deleted account",
        metadata={"permanent": True},
    )
    assert event.entity_type == "account"
    assert event.action is Action.DELETE
    assert event.metadata == {"permanent": True}


async def test_emit_expresses_the_finalize_shape() -> None:
    # finalize: parametrized entity_type/action with dict[str, object] metadata.
    metadata: dict[str, object] = {
        "revision": 3,
        "pdf_object_key": "resumes/1/3.pdf",
        "template": "modern",
    }
    event = await _capture_emitted(
        user_id=1,
        actor=human_actor(),
        entity_type="resume",
        entity_id=55,
        action=Action.FINALIZE,
        summary="Finalized resume",
        metadata=metadata,
    )
    assert event.action is Action.FINALIZE
    assert event.entity_type == "resume"
    assert event.metadata == metadata


def test_get_events_returns_the_wired_publisher() -> None:
    app = Starlette()
    publisher = WriteEventPublisher()
    app.state.events = publisher
    assert get_events(app) is publisher


def test_get_events_raises_when_the_seam_is_unset() -> None:
    # Fail loud: an unset seam is a wiring bug, not a silent audit/feed drop.
    with pytest.raises(RuntimeError):
        get_events(Starlette())


def test_get_events_raises_when_the_seam_is_the_wrong_type() -> None:
    app = Starlette()
    app.state.events = object()
    with pytest.raises(RuntimeError):
        get_events(app)
