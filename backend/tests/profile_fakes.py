"""In-memory test doubles and factories for the profile-sources domain.

The service is tested sociably: the real :class:`SourceService` runs over this
in-memory repository (substituted at the only true external boundary, Postgres),
the real :class:`WriteEventPublisher` seam wired with a capturing consumer, and a
fake session that records the ``transaction`` boundary's commit/rollback. The repo
mirrors what the database assigns on insert (the server-minted id and the
``sort_order`` server default) so the service can project a complete read shape
without a database.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from floresu.profile.models import Source, SourceKind, SourceSubtype
from floresu.profile.schemas import (
    CertificationWrite,
    EducationWrite,
    ProjectWrite,
    RoleWrite,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

# The enum's declared order, which Postgres uses for ``ORDER BY kind``.
_KIND_ORDER = {kind: index for index, kind in enumerate(SourceKind)}


class InMemorySourceRepository:
    """A dict-backed :class:`SourceRepository` with real ids and ownership scoping."""

    def __init__(self) -> None:
        self._sources: dict[int, Source] = {}
        self._subtypes: dict[int, SourceSubtype] = {}
        self._next_id = 1

    async def add(self, source: Source, subtype: SourceSubtype) -> None:
        source.id = self._next_id
        self._next_id += 1
        # Mirror the ``sort_order`` server default the real table applies on insert.
        if source.sort_order is None:
            source.sort_order = 0
        subtype.source_id = source.id
        self._sources[source.id] = source
        self._subtypes[source.id] = subtype

    async def get(self, user_id: int, source_id: int) -> Source | None:
        source = self._sources.get(source_id)
        if source is None or source.user_id != user_id:
            return None
        return source

    async def get_detail(self, user_id: int, source_id: int) -> tuple[Source, SourceSubtype] | None:
        source = await self.get(user_id, source_id)
        if source is None:
            return None
        return source, self._subtypes[source_id]

    async def list(
        self, user_id: int, *, kind: SourceKind | None, include_archived: bool, limit: int
    ) -> Sequence[Source]:
        rows = [s for s in self._sources.values() if s.user_id == user_id]
        if kind is not None:
            rows = [s for s in rows if s.kind == kind]
        if not include_archived:
            rows = [s for s in rows if s.archived_at is None]
        rows.sort(key=lambda s: (_KIND_ORDER[s.kind], s.sort_order, s.id))
        return rows[:limit]

    async def active_section(self, user_id: int, kind: SourceKind) -> Sequence[Source]:
        rows = [
            s
            for s in self._sources.values()
            if s.user_id == user_id and s.kind == kind and s.archived_at is None
        ]
        rows.sort(key=lambda s: (s.sort_order, s.id))
        return rows


def build_role_write(**overrides: Any) -> RoleWrite:
    base: dict[str, Any] = {
        "display_label": "Senior Engineer, Acme",
        "company": "Acme",
        "job_title": "Senior Engineer",
        "title_aliases": ["Sr. SWE"],
        "location": "Remote",
        "date_start": "2020-01-01",
        "date_end": None,
        "summary": "Built things.",
    }
    base.update(overrides)
    return RoleWrite(**base)


def build_project_write(**overrides: Any) -> ProjectWrite:
    base: dict[str, Any] = {
        "display_label": "Floresu",
        "links": ["https://example.com/floresu"],
        "summary": "A career tracker.",
    }
    base.update(overrides)
    return ProjectWrite(**base)


def build_certification_write(**overrides: Any) -> CertificationWrite:
    base: dict[str, Any] = {
        "display_label": "AWS Solutions Architect",
        "issuer": "Amazon Web Services",
        "credential_id": "ABC-123",
        "date_start": "2023-06-01",
    }
    base.update(overrides)
    return CertificationWrite(**base)


def build_education_write(**overrides: Any) -> EducationWrite:
    base: dict[str, Any] = {
        "display_label": "BSc Computer Science",
        "institution": "State University",
        "degree": "BSc",
        "field": "Computer Science",
        "date_start": "2016-09-01",
        "date_end": "2020-05-01",
    }
    base.update(overrides)
    return EducationWrite(**base)
