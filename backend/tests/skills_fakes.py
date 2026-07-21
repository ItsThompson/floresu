"""In-memory test doubles and factories for the skills domain.

The service is tested sociably: the real :class:`SkillService` runs over this
in-memory repository (substituted at the only true external boundary, Postgres),
the real :class:`WriteEventPublisher` seam wired with a capturing consumer, and the
profile :class:`FakeSession` recording the ``transaction`` boundary. The repo
mirrors what the database assigns on insert (the server-minted id and the
``sort_order`` server default) and enforces ``UNIQUE (user_id, name)`` by raising a
unique-violation ``IntegrityError`` so the service's Conflict mapping is exercised
without a database. Usage counts are seeded directly, standing in for the
cross-domain worklog-tag query the real repository runs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import IntegrityError

from floresu.profile.skills.models import Skill
from floresu.profile.skills.schemas import SkillWrite

# The profile FakeSession + capturing publisher are the canonical profile-family
# test doubles; skills is a profile-family entity, so it reuses them rather than
# re-declaring an identical session/publisher stand-in.
from tests.profile_fakes import FakeSession, capturing_publisher

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["FakeSession", "InMemorySkillRepository", "build_skill_write", "capturing_publisher"]


class _UniqueOrigError(Exception):
    """A stand-in DBAPI error carrying the Postgres unique-violation SQLSTATE."""

    def __init__(self) -> None:
        self.sqlstate = "23505"
        super().__init__(self.sqlstate)


class InMemorySkillRepository:
    """A dict-backed :class:`SkillRepository` with real ids, scoping, and unique names."""

    def __init__(self) -> None:
        self._skills: dict[int, Skill] = {}
        self._next_id = 1
        self._usage: dict[tuple[int, str], int] = {}

    def set_usage(self, user_id: int, name: str, count: int) -> None:
        """Seed the usage count the cross-domain worklog-tag query would return."""
        self._usage[(user_id, name)] = count

    async def add(self, skill: Skill) -> None:
        if any(
            other.user_id == skill.user_id and other.name == skill.name
            for other in self._skills.values()
        ):
            # Mirror the ``UNIQUE (user_id, name)`` breach the real table raises.
            raise IntegrityError("INSERT INTO skills", {}, orig=_UniqueOrigError())
        skill.id = self._next_id
        self._next_id += 1
        if skill.sort_order is None:
            skill.sort_order = 0
        self._skills[skill.id] = skill

    async def get(self, user_id: int, skill_id: int) -> Skill | None:
        skill = self._skills.get(skill_id)
        if skill is None or skill.user_id != user_id:
            return None
        return skill

    async def list(self, user_id: int, *, include_archived: bool, limit: int) -> Sequence[Skill]:
        rows = [s for s in self._skills.values() if s.user_id == user_id]
        if not include_archived:
            rows = [s for s in rows if s.archived_at is None]
        rows.sort(key=lambda s: (s.sort_order, s.id))
        return rows[:limit]

    async def active_section(self, user_id: int) -> Sequence[Skill]:
        rows = [s for s in self._skills.values() if s.user_id == user_id and s.archived_at is None]
        rows.sort(key=lambda s: (s.sort_order, s.id))
        return rows

    async def usage_counts(self, user_id: int, names: Sequence[str]) -> dict[str, int]:
        return {name: self._usage.get((user_id, name), 0) for name in names}


def build_skill_write(**overrides: Any) -> SkillWrite:
    base: dict[str, Any] = {"name": "Python"}
    base.update(overrides)
    return SkillWrite(**base)
