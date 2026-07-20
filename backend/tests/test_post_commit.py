"""The deferred post-commit queue (:mod:`floresu.core.post_commit`).

The queue lives on ``session.info`` so each request's session carries its own
deferred side channels. These unit tests use a fake session (only ``.info`` is
touched) to prove the enqueue / discard / run contract and, critically, that a
failing task is isolated so a down side channel never propagates out of the
already-committed write.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from floresu.core.post_commit import discard_post_commit, enqueue_post_commit, run_post_commit

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class _FakeSession:
    def __init__(self) -> None:
        self.info: dict[str, Any] = {}


def _session() -> AsyncSession:
    return cast("AsyncSession", _FakeSession())


async def test_run_executes_queued_tasks_in_order_then_clears_them() -> None:
    session = _session()
    ran: list[str] = []

    def append(name: str) -> None:
        async def task() -> None:
            ran.append(name)

        enqueue_post_commit(session, task)

    append("first")
    append("second")

    await run_post_commit(session)
    assert ran == ["first", "second"]

    # The queue is drained: a second run is a no-op.
    await run_post_commit(session)
    assert ran == ["first", "second"]


async def test_a_failing_task_is_isolated_and_does_not_stop_siblings() -> None:
    session = _session()
    ran: list[str] = []

    async def failing() -> None:
        raise RuntimeError("side channel down")

    async def ok() -> None:
        ran.append("ok")

    enqueue_post_commit(session, failing)
    enqueue_post_commit(session, ok)

    # run_post_commit swallows the failure and still runs the sibling.
    await run_post_commit(session)
    assert ran == ["ok"]


async def test_discard_drops_queued_tasks_without_running_them() -> None:
    session = _session()
    ran: list[str] = []

    async def task() -> None:
        ran.append("ran")

    enqueue_post_commit(session, task)
    discard_post_commit(session)

    await run_post_commit(session)
    assert ran == []
