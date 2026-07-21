"""Wire schemas for skills: the write body, the reorder input, and the read shape.

A write (:class:`SkillWrite`) carries only a ``name``; ``sort_order`` is set by
reorder and ``archived_at`` by archive/restore, and the id is server-minted. The
read (:class:`SkillRead`) adds the ``usage_count`` the service computes from tag
matches, so the count is never accepted on a write and never stored.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from floresu.profile.skills.models import Skill


class SkillWrite(BaseModel):
    """The create/rename body: a skill is defined by its curated ``name``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)


class SkillReorderRequest(BaseModel):
    """A reorder: the full ordered id list for the user's active skills."""

    model_config = ConfigDict(extra="forbid")

    skill_ids: list[int] = Field(min_length=1)


class SkillRead(BaseModel):
    """A skill with its derived usage count (computed from tag matches, not stored)."""

    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    usage_count: int
    sort_order: int
    archived_at: datetime | None


def to_read(skill: Skill, usage_count: int) -> SkillRead:
    """Project a ``skills`` ORM row plus its computed usage onto the read shape."""
    return SkillRead(
        id=skill.id,
        name=skill.name,
        usage_count=usage_count,
        sort_order=skill.sort_order,
        archived_at=skill.archived_at,
    )
