"""In-memory test doubles and factories for the library domain.

The service is tested sociably: the real :class:`LibraryService` runs over this
in-memory repository (substituted at the only true external boundary, Postgres),
the real :class:`WriteEventPublisher` seam wired with a capturing consumer, and a
fake session that records the ``transaction`` boundary's commit/rollback. The repo
mirrors what the database assigns on insert (server-minted ids) and orders reads
the way the real queries do (bullets newest-first, edge ids ascending). Source and
worklog ownership are seeded via :meth:`InMemoryLibraryRepository.own_source` /
:meth:`own_worklog`, since a bullet frames items other domains own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from floresu.core.events import WriteEvent, WriteEventPublisher
from floresu.library.models import Bulletpoint
from floresu.library.schemas import BulletpointWrite

if TYPE_CHECKING:
    from collections.abc import Sequence


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


class InMemoryLibraryRepository:
    """A dict-backed :class:`LibraryRepository` with real ids and ownership scoping."""

    def __init__(self) -> None:
        self._bullets: dict[int, Bulletpoint] = {}
        self._next_id = 1
        self._sources_by_bullet: dict[int, list[int]] = {}
        self._worklogs_by_bullet: dict[int, list[int]] = {}
        self._owned_sources: dict[int, set[int]] = {}
        self._owned_worklogs: dict[int, set[int]] = {}

    def own_source(self, user_id: int, source_id: int) -> None:
        """Seed a source the user owns, so a bullet may frame it."""
        self._owned_sources.setdefault(user_id, set()).add(source_id)

    def own_worklog(self, user_id: int, worklog_id: int) -> None:
        """Seed a worklog entry the user owns, so a bullet may frame it."""
        self._owned_worklogs.setdefault(user_id, set()).add(worklog_id)

    async def add(self, bullet: Bulletpoint) -> None:
        bullet.id = self._next_id
        self._next_id += 1
        # Mirror the ``revision`` server default the real table applies on insert.
        if bullet.revision is None:
            bullet.revision = 1
        self._bullets[bullet.id] = bullet

    async def get(self, user_id: int, bullet_id: int) -> Bulletpoint | None:
        bullet = self._bullets.get(bullet_id)
        if bullet is None or bullet.user_id != user_id:
            return None
        return bullet

    async def list_bullets(
        self, user_id: int, *, include_archived: bool, limit: int
    ) -> Sequence[Bulletpoint]:
        rows = [bullet for bullet in self._bullets.values() if bullet.user_id == user_id]
        if not include_archived:
            rows = [bullet for bullet in rows if bullet.archived_at is None]
        rows.sort(key=lambda bullet: bullet.id, reverse=True)
        return rows[:limit]

    async def owned_source_ids(self, user_id: int, source_ids: Sequence[int]) -> set[int]:
        owned = self._owned_sources.get(user_id, set())
        return {source_id for source_id in source_ids if source_id in owned}

    async def owned_worklog_ids(self, user_id: int, worklog_ids: Sequence[int]) -> set[int]:
        owned = self._owned_worklogs.get(user_id, set())
        return {worklog_id for worklog_id in worklog_ids if worklog_id in owned}

    async def set_sources(self, bullet_id: int, source_ids: Sequence[int]) -> None:
        self._sources_by_bullet[bullet_id] = list(source_ids)

    async def set_worklogs(self, bullet_id: int, worklog_ids: Sequence[int]) -> None:
        self._worklogs_by_bullet[bullet_id] = list(worklog_ids)

    async def source_ids_by_bullet(self, bullet_ids: Sequence[int]) -> dict[int, list[int]]:
        sources: dict[int, list[int]] = {}
        for bullet_id in bullet_ids:
            found = sorted(self._sources_by_bullet.get(bullet_id, []))
            if found:
                sources[bullet_id] = found
        return sources

    async def worklog_ids_by_bullet(self, bullet_ids: Sequence[int]) -> dict[int, list[int]]:
        worklogs: dict[int, list[int]] = {}
        for bullet_id in bullet_ids:
            found = sorted(self._worklogs_by_bullet.get(bullet_id, []))
            if found:
                worklogs[bullet_id] = found
        return worklogs


def capturing_publisher() -> tuple[WriteEventPublisher, list[WriteEvent]]:
    """The real publisher seam wired with a capturing transactional consumer."""
    captured: list[WriteEvent] = []

    async def consume(_session: Any, event: WriteEvent) -> None:
        captured.append(event)

    return WriteEventPublisher(transactional=[consume]), captured


class InMemoryBulletUsageCounter:
    """A seedable :class:`BulletUsageCounter` double that records each call's ids.

    Mirrors the grouped-count contract of the real ``resume_bullet_ref`` query: a
    seeded id returns its count, an id with no reference is absent from the result
    (so the call site defaults it to 0), and an empty input returns an empty map.
    ``calls`` records the id lists passed, so a test can assert one batched call per
    list read rather than a per-bullet N+1.
    """

    def __init__(self) -> None:
        self._counts: dict[int, int] = {}
        self.calls: list[list[int]] = []

    def set_count(self, bullet_id: int, count: int) -> None:
        """Seed how many resumes reference a bullet."""
        self._counts[bullet_id] = count

    async def used_in_counts(self, bullet_ids: Sequence[int]) -> dict[int, int]:
        self.calls.append(list(bullet_ids))
        return {
            bullet_id: self._counts[bullet_id]
            for bullet_id in bullet_ids
            if self._counts.get(bullet_id, 0) > 0
        }


def build_bullet_write(**overrides: Any) -> BulletpointWrite:
    base: dict[str, Any] = {
        "text": "Cut p99 checkout latency 40% by sharding the write path.",
        "source_ids": [],
        "worklog_ids": [],
    }
    base.update(overrides)
    return BulletpointWrite(**base)
