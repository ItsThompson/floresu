"""SkillService: the single home for skill lifecycle rules and transactions.

Every skill write runs here and nowhere else, so the web and agent adapters stay
thin and provenance is uniform. Each mutate wraps its work in the ``transaction``
boundary and publishes exactly one :class:`WriteEvent` through the write-event
seam from *inside* that boundary, so the audit row (the seam's transactional
consumer) commits or rolls back atomically with the write. The resolved
:class:`Actor` (human vs named agent) is carried into every event.

Skills are curated: create adds a named skill (a duplicate name is a Conflict, not
a silent reuse: a tag is never auto-promoted to a skill), update renames it,
reorder assigns ``sort_order`` by submitted position, and archive/restore toggle
the soft state. The usage count on every read is computed from tag matches, so it
is never stored and always reflects the current tags.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from floresu.core.conflicts import conflict_on_duplicate
from floresu.core.db import transaction
from floresu.core.errors import Conflict, NotFound, Validation
from floresu.core.events import Action, emit_write_event
from floresu.core.identity import resolve_user_pk
from floresu.core.logging import get_logger
from floresu.core.observability import track_failures
from floresu.profile.injection import Clock, utcnow
from floresu.profile.skills.config import DEFAULT_LIST_LIMIT, ENTITY_TYPE
from floresu.profile.skills.models import Skill
from floresu.profile.skills.schemas import SkillRead, to_read

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.actor import Actor
    from floresu.core.events import WriteEventPublisher
    from floresu.profile.skills.repository import SkillRepository
    from floresu.profile.skills.schemas import SkillReorderRequest, SkillWrite

_log = get_logger("floresu-skills")


@track_failures("skills")
class SkillService:
    """Business rules for the curated skills list and its derived usage count."""

    def __init__(
        self,
        session: AsyncSession,
        repo: SkillRepository,
        publisher: WriteEventPublisher,
        *,
        clock: Clock = utcnow,
    ) -> None:
        self._session = session
        self._repo = repo
        self._publisher = publisher
        self._clock = clock

    async def create(self, user_id: str, actor: Actor, write: SkillWrite) -> SkillRead:
        """Add a curated skill; a duplicate name is a Conflict (never auto-promoted)."""
        pk = resolve_user_pk(user_id)
        skill = Skill(user_id=pk, name=write.name)
        async with (
            conflict_on_duplicate(_duplicate_message(write.name)),
            transaction(self._session),
        ):
            await self._repo.add(skill)
            await self._publish(pk, actor, skill.id, Action.CREATE, _created_summary(skill))
        return await self._read(pk, skill)

    async def get(self, user_id: str, skill_id: int) -> SkillRead:
        """Read one skill with its computed usage count."""
        pk = resolve_user_pk(user_id)
        skill = await self._require(pk, skill_id)
        return await self._read(pk, skill)

    async def list_skills(
        self, user_id: str, *, include_archived: bool = False, limit: int = DEFAULT_LIST_LIMIT
    ) -> list[SkillRead]:
        """List skills in curated order; active-only by default, usage batch-computed."""
        pk = resolve_user_pk(user_id)
        skills = await self._repo.list(pk, include_archived=include_archived, limit=limit)
        return await self._read_many(pk, skills)

    async def update(
        self, user_id: str, skill_id: int, actor: Actor, write: SkillWrite
    ) -> SkillRead:
        """Rename a skill; renaming onto another skill's name is a Conflict."""
        pk = resolve_user_pk(user_id)
        skill = await self._require(pk, skill_id)
        async with (
            conflict_on_duplicate(_duplicate_message(write.name)),
            transaction(self._session),
        ):
            skill.name = write.name
            await self._publish(pk, actor, skill.id, Action.UPDATE, _edited_summary(skill))
        return await self._read(pk, skill)

    async def archive(self, user_id: str, skill_id: int, actor: Actor) -> SkillRead:
        """Soft-archive: stamp ``archived_at`` so the skill drops from active lists."""
        pk = resolve_user_pk(user_id)
        skill = await self._require(pk, skill_id)
        if skill.archived_at is not None:
            _log.warning("skill_archive_conflict", skill_id=skill_id)
            raise Conflict("This skill is already archived.")
        async with transaction(self._session):
            skill.archived_at = self._clock()
            await self._publish(pk, actor, skill.id, Action.ARCHIVE, _archived_summary(skill))
        return await self._read(pk, skill)

    async def restore(self, user_id: str, skill_id: int, actor: Actor) -> SkillRead:
        """Clear ``archived_at`` so an archived skill returns to active lists."""
        pk = resolve_user_pk(user_id)
        skill = await self._require(pk, skill_id)
        if skill.archived_at is None:
            _log.warning("skill_restore_conflict", skill_id=skill_id)
            raise Conflict("This skill is not archived.")
        async with transaction(self._session):
            skill.archived_at = None
            await self._publish(pk, actor, skill.id, Action.RESTORE, _restored_summary(skill))
        return await self._read(pk, skill)

    async def reorder(
        self, user_id: str, actor: Actor, request: SkillReorderRequest
    ) -> list[SkillRead]:
        """Persist ``sort_order`` by submitted position over the full active list.

        The submit must be a permutation of the user's full active skill list:
        every active skill, listed exactly once. A partial submit is rejected, so
        ``sort_order`` can never end up duplicated or partially applied.
        """
        pk = resolve_user_pk(user_id)
        ordered_ids = request.skill_ids
        if len(set(ordered_ids)) != len(ordered_ids):
            raise Validation("The reorder contains duplicate skill ids.")
        section = await self._repo.active_section(pk)
        by_id = {skill.id: skill for skill in section}
        if set(ordered_ids) != set(by_id):
            raise Validation(
                "A reorder must list every active skill exactly once.",
                fields={
                    "skill_ids": (
                        f"Expected the {len(by_id)} active skill(s); got {len(ordered_ids)}."
                    )
                },
            )
        async with transaction(self._session):
            for position, skill_id in enumerate(ordered_ids):
                by_id[skill_id].sort_order = position
            await self._publish(
                pk,
                actor,
                ordered_ids[0],
                Action.REORDER,
                f"Reordered {len(ordered_ids)} skills",
                metadata={"order": ordered_ids},
            )
        return await self._read_many(pk, [by_id[skill_id] for skill_id in ordered_ids])

    async def _require(self, user_pk: int, skill_id: int) -> Skill:
        skill = await self._repo.get(user_pk, skill_id)
        if skill is None:
            raise _not_found(skill_id)
        return skill

    async def _read(self, user_pk: int, skill: Skill) -> SkillRead:
        counts = await self._repo.usage_counts(user_pk, [skill.name])
        return to_read(skill, counts.get(skill.name, 0))

    async def _read_many(self, user_pk: int, skills: Sequence[Skill]) -> list[SkillRead]:
        counts = await self._repo.usage_counts(user_pk, [skill.name for skill in skills])
        return [to_read(skill, counts.get(skill.name, 0)) for skill in skills]

    async def _publish(
        self,
        user_pk: int,
        actor: Actor,
        entity_id: int,
        action: Action,
        summary: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await emit_write_event(
            self._publisher,
            self._session,
            user_id=user_pk,
            actor=actor,
            entity_type=ENTITY_TYPE,
            entity_id=entity_id,
            action=action,
            summary=summary,
            metadata=metadata,
        )


def _not_found(skill_id: int) -> NotFound:
    # 404-over-403: a skill another account owns is scoped out of the read, so a
    # miss is indistinguishable from "does not exist" (no existence leak).
    return NotFound(f"No skill with id {skill_id}.")


def _duplicate_message(name: str) -> str:
    return f"A skill named “{name}” already exists."


def _created_summary(skill: Skill) -> str:
    return f"Added skill “{skill.name}”"


def _edited_summary(skill: Skill) -> str:
    return f"Renamed skill to “{skill.name}”"


def _archived_summary(skill: Skill) -> str:
    return f"Archived skill “{skill.name}”"


def _restored_summary(skill: Skill) -> str:
    return f"Restored skill “{skill.name}”"
