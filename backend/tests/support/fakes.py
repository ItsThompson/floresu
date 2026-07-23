"""Test doubles shared by every write-publishing domain's fake module.

Two doubles are identical across the domain ``*_fakes.py`` modules: a no-op session
that records the ``transaction`` boundary, and the real write-event publisher wired
with a capturing consumer. They live here once so each domain module keeps only its
own repository fake, and the tests import the shared doubles from here rather than
re-declaring an identical stand-in per domain. The publisher subclasses the real
seam, so tests still exercise the real fan-out (sociable) rather than a fake seam.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from floresu.core.events import WriteEvent, WriteEventPublisher

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class FakeSession:
    """A no-op stand-in for ``AsyncSession`` recording the transaction boundary.

    Carries ``info`` because the ``transaction`` boundary drains the session's
    post-commit queue (see :mod:`floresu.core.post_commit`) on a clean exit.
    """

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.info: dict[str, Any] = {}

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class CapturingWriteEventPublisher(WriteEventPublisher):
    """The real publisher seam wired with a capturing transactional consumer.

    Subclasses the production publisher so a service under test fans events out
    through the real seam logic, while every published event is recorded on
    :attr:`captured` for assertions. The capturing consumer records nothing durable
    (returns ``None``), so the post-commit side channels stay dormant, matching a
    publisher wired with no audit consumer.
    """

    def __init__(self) -> None:
        self.captured: list[WriteEvent] = []

        async def capture(_session: AsyncSession, event: WriteEvent) -> None:
            self.captured.append(event)

        super().__init__(transactional=[capture])
