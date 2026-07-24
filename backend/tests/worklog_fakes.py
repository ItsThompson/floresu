"""In-memory test doubles and factories for the worklog domain.

The service is tested sociably: the real :class:`WorklogService` runs over this
in-memory repository (substituted at the only true external boundary, Postgres),
the real :class:`WriteEventPublisher` seam wired with a capturing consumer, and a
fake session that records the ``transaction`` boundary's commit/rollback. The repo
mirrors what the database assigns on insert (server-minted ids) and orders reads
the way the real queries do (entries newest-first, tags by label, sources by id).
Source ownership is seeded via :meth:`InMemoryWorklogRepository.own_source`, since
worklog attaches to sources another domain owns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from floresu.worklog.models import Tag, WorklogEntry
from floresu.worklog.schemas import WorklogWrite
from tests.support.fakes import owned_from

if TYPE_CHECKING:
    from collections.abc import Sequence


class InMemoryWorklogRepository:
    """A dict-backed :class:`WorklogRepository` with real ids and ownership scoping."""

    def __init__(self) -> None:
        self._entries: dict[int, WorklogEntry] = {}
        self._next_entry_id = 1
        self._tags: dict[int, Tag] = {}
        self._next_tag_id = 1
        self._sources_by_worklog: dict[int, list[int]] = {}
        self._tags_by_worklog: dict[int, list[int]] = {}
        self._owned_sources: dict[int, set[int]] = {}
        self._bullets_by_worklog: dict[int, list[int]] = {}
        self._archived_bullets: set[int] = set()

    def own_source(self, user_id: int, source_id: int) -> None:
        """Seed a source the user owns, so an entry may attach it."""
        self._owned_sources.setdefault(user_id, set()).add(source_id)

    def frame_bullet(self, worklog_id: int, bullet_id: int, *, archived: bool = False) -> None:
        """Seed a canonical bullet that frames a worklog entry (test setup).

        Mirrors a ``bullet_worklog`` edge plus the bullet's archive state, so
        :meth:`bullet_ids_by_worklog` can exclude an archived bullet the way the
        real join does. A bullet another domain owns is framed here, not added to
        this repository's own tables.
        """
        self._bullets_by_worklog.setdefault(worklog_id, []).append(bullet_id)
        if archived:
            self._archived_bullets.add(bullet_id)

    async def add(self, entry: WorklogEntry) -> None:
        entry.id = self._next_entry_id
        self._next_entry_id += 1
        self._entries[entry.id] = entry

    async def get(self, user_id: int, worklog_id: int) -> WorklogEntry | None:
        entry = self._entries.get(worklog_id)
        if entry is None or entry.user_id != user_id:
            return None
        return entry

    async def list_entries(
        self, user_id: int, *, include_archived: bool, limit: int
    ) -> Sequence[WorklogEntry]:
        rows = [entry for entry in self._entries.values() if entry.user_id == user_id]
        if not include_archived:
            rows = [entry for entry in rows if entry.archived_at is None]
        rows.sort(key=lambda entry: (entry.entry_date, entry.id), reverse=True)
        return rows[:limit]

    async def owned_source_ids(self, user_id: int, source_ids: Sequence[int]) -> set[int]:
        return owned_from(self._owned_sources.get(user_id, set()), source_ids)

    async def get_or_create_tag(self, user_id: int, label: str) -> Tag:
        for tag in self._tags.values():
            if tag.user_id == user_id and tag.label == label:
                return tag
        tag = Tag(user_id=user_id, label=label)
        tag.id = self._next_tag_id
        self._next_tag_id += 1
        self._tags[tag.id] = tag
        return tag

    async def list_tags(self, user_id: int) -> Sequence[Tag]:
        rows = [tag for tag in self._tags.values() if tag.user_id == user_id]
        rows.sort(key=lambda tag: tag.label)
        return rows

    async def set_sources(self, worklog_id: int, source_ids: Sequence[int]) -> None:
        self._sources_by_worklog[worklog_id] = list(source_ids)

    async def set_tags(self, worklog_id: int, tag_ids: Sequence[int]) -> None:
        self._tags_by_worklog[worklog_id] = list(tag_ids)

    async def tag_labels_by_worklog(self, worklog_ids: Sequence[int]) -> dict[int, list[str]]:
        labels: dict[int, list[str]] = {}
        for worklog_id in worklog_ids:
            found = sorted(
                self._tags[tid].label for tid in self._tags_by_worklog.get(worklog_id, [])
            )
            if found:
                labels[worklog_id] = found
        return labels

    async def source_ids_by_worklog(self, worklog_ids: Sequence[int]) -> dict[int, list[int]]:
        sources: dict[int, list[int]] = {}
        for worklog_id in worklog_ids:
            found = sorted(self._sources_by_worklog.get(worklog_id, []))
            if found:
                sources[worklog_id] = found
        return sources

    async def bullet_ids_by_worklog(self, worklog_ids: Sequence[int]) -> dict[int, list[int]]:
        # Mirror the real archived-excluding join: the active (non-archived) bullets
        # framing each entry, ordered by bullet id, and absent for an entry no
        # active bullet frames.
        bullets: dict[int, list[int]] = {}
        for worklog_id in worklog_ids:
            active = sorted(
                bullet_id
                for bullet_id in self._bullets_by_worklog.get(worklog_id, [])
                if bullet_id not in self._archived_bullets
            )
            if active:
                bullets[worklog_id] = active
        return bullets


def build_worklog_write(**overrides: Any) -> WorklogWrite:
    base: dict[str, Any] = {
        "title": "Shipped the search API",
        "entry_date": "2026-01-15",
        "description": "Wired hybrid search behind the internal boundary.",
        "tags": [],
        "source_ids": [],
    }
    base.update(overrides)
    return WorklogWrite(**base)
