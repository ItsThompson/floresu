"""SkillService business rules, through its public methods with an in-memory
repository, the real write-event seam (capturing consumer), and the profile fake
session recording the transaction boundary (sociable)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from floresu.core.actor import Actor, ActorType
from floresu.core.errors import Conflict, NotFound, Unauthorized, Validation
from floresu.core.events import Action, WriteEvent
from floresu.profile.injection import Clock
from floresu.profile.skills.schemas import SkillReorderRequest
from floresu.profile.skills.service import SkillService
from tests.skills_fakes import (
    FakeSession,
    InMemorySkillRepository,
    build_skill_write,
    capturing_publisher,
)

_USER = "1"
_HUMAN = Actor(type=ActorType.HUMAN)
_AGENT = Actor(type=ActorType.AGENT, label="claude")


def _service(
    *, clock: Clock | None = None
) -> tuple[SkillService, InMemorySkillRepository, FakeSession, list[WriteEvent]]:
    repo = InMemorySkillRepository()
    session = FakeSession()
    publisher, captured = capturing_publisher()
    kwargs = {"clock": clock} if clock is not None else {}
    service = SkillService(session, repo, publisher, **kwargs)  # type: ignore[arg-type]
    return service, repo, session, captured


async def test_create_adds_a_skill_and_publishes_create() -> None:
    service, _, session, captured = _service()
    skill = await service.create(_USER, _HUMAN, build_skill_write(name="Rust"))

    assert skill.id >= 1
    assert skill.name == "Rust"
    assert skill.sort_order == 0
    assert skill.usage_count == 0
    assert skill.archived_at is None

    assert len(captured) == 1
    event = captured[0]
    assert event.action is Action.CREATE
    assert event.entity_type == "skill"
    assert event.entity_id == skill.id
    assert event.user_id == 1
    assert event.actor == _HUMAN
    assert event.summary is not None and "Rust" in event.summary
    assert session.commits == 1


async def test_a_tag_is_never_auto_promoted_a_duplicate_name_is_a_conflict() -> None:
    # A skill is added deliberately; adding one whose name already exists conflicts
    # rather than silently reusing it (skills are curated, not derived from tags).
    service, _, _, captured = _service()
    await service.create(_USER, _HUMAN, build_skill_write(name="Python"))
    captured.clear()
    with pytest.raises(Conflict):
        await service.create(_USER, _HUMAN, build_skill_write(name="Python"))
    assert captured == []


async def test_usage_count_is_computed_from_tag_matches_not_stored() -> None:
    service, repo, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_skill_write(name="Python"))
    assert created.usage_count == 0  # no worklog tags yet

    # Simulate three worklog entries tagged "Python"; the count reflects it live.
    repo.set_usage(1, "Python", 3)
    fetched = await service.get(_USER, created.id)
    assert fetched.usage_count == 3


async def test_create_reflects_a_preexisting_tag_usage() -> None:
    # A skill's name may already match tags used before it was curated.
    service, repo, _, _ = _service()
    repo.set_usage(1, "Docker", 2)
    created = await service.create(_USER, _HUMAN, build_skill_write(name="Docker"))
    assert created.usage_count == 2


async def test_rename_records_an_update() -> None:
    service, _, session, captured = _service()
    created = await service.create(_USER, _HUMAN, build_skill_write(name="Go"))
    await service.create(_USER, _HUMAN, build_skill_write(name="Rust"))
    captured.clear()

    renamed = await service.update(_USER, created.id, _HUMAN, build_skill_write(name="Golang"))
    assert renamed.name == "Golang"
    assert len(captured) == 1
    assert captured[0].action is Action.UPDATE
    assert session.commits == 3  # two creates + one rename
    # Renaming onto another skill's name conflicts via the unique constraint; that
    # fires at commit, so it is proven end to end in the integration suite.


async def test_agent_writes_carry_the_named_agent_actor() -> None:
    service, _, _, captured = _service()
    await service.create(_USER, _AGENT, build_skill_write())
    assert captured[0].actor == _AGENT
    assert captured[0].actor.label == "claude"


async def test_get_and_mutations_of_a_missing_skill_are_not_found() -> None:
    service, _, _, _ = _service()
    with pytest.raises(NotFound):
        await service.get(_USER, 999)
    with pytest.raises(NotFound):
        await service.update(_USER, 999, _HUMAN, build_skill_write())
    with pytest.raises(NotFound):
        await service.archive(_USER, 999, _HUMAN)
    with pytest.raises(NotFound):
        await service.restore(_USER, 999, _HUMAN)


async def test_another_users_skill_is_not_found_no_existence_leak() -> None:
    service, _, _, _ = _service()
    mine = await service.create(_USER, _HUMAN, build_skill_write())
    with pytest.raises(NotFound):
        await service.get("2", mine.id)


async def test_archive_hides_from_active_lists_and_records_archive() -> None:
    clock = _FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    service, _, _, captured = _service(clock=clock)
    created = await service.create(_USER, _HUMAN, build_skill_write())
    captured.clear()

    archived = await service.archive(_USER, created.id, _HUMAN)
    assert archived.archived_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert captured[0].action is Action.ARCHIVE

    assert await service.list_skills(_USER) == []
    including = await service.list_skills(_USER, include_archived=True)
    assert [s.id for s in including] == [created.id]


async def test_double_archive_is_a_conflict() -> None:
    service, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_skill_write())
    await service.archive(_USER, created.id, _HUMAN)
    with pytest.raises(Conflict):
        await service.archive(_USER, created.id, _HUMAN)


async def test_restore_returns_a_skill_to_active_lists() -> None:
    service, _, _, captured = _service()
    created = await service.create(_USER, _HUMAN, build_skill_write())
    await service.archive(_USER, created.id, _HUMAN)
    captured.clear()

    restored = await service.restore(_USER, created.id, _HUMAN)
    assert restored.archived_at is None
    assert captured[0].action is Action.RESTORE
    assert [s.id for s in await service.list_skills(_USER)] == [created.id]


async def test_restore_of_an_active_skill_is_a_conflict() -> None:
    service, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_skill_write())
    with pytest.raises(Conflict):
        await service.restore(_USER, created.id, _HUMAN)


async def test_reorder_persists_sort_order() -> None:
    service, _, _, captured = _service()
    first = await service.create(_USER, _HUMAN, build_skill_write(name="A"))
    second = await service.create(_USER, _HUMAN, build_skill_write(name="B"))
    third = await service.create(_USER, _HUMAN, build_skill_write(name="C"))
    captured.clear()

    new_order = [third.id, first.id, second.id]
    result = await service.reorder(_USER, _HUMAN, SkillReorderRequest(skill_ids=new_order))
    assert [s.id for s in result] == new_order

    listed = await service.list_skills(_USER)
    assert [s.id for s in listed] == new_order
    assert [s.sort_order for s in listed] == [0, 1, 2]

    assert len(captured) == 1
    assert captured[0].action is Action.REORDER
    assert captured[0].metadata == {"order": new_order}


async def test_reorder_rejects_a_partial_list() -> None:
    service, _, _, captured = _service()
    first = await service.create(_USER, _HUMAN, build_skill_write(name="A"))
    await service.create(_USER, _HUMAN, build_skill_write(name="B"))
    third = await service.create(_USER, _HUMAN, build_skill_write(name="C"))
    captured.clear()

    with pytest.raises(Validation):
        await service.reorder(_USER, _HUMAN, SkillReorderRequest(skill_ids=[third.id, first.id]))
    assert captured == []


async def test_reorder_rejects_duplicate_and_unknown_ids() -> None:
    service, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_skill_write())
    with pytest.raises(Validation):
        await service.reorder(
            _USER, _HUMAN, SkillReorderRequest(skill_ids=[created.id, created.id])
        )
    with pytest.raises(Validation):
        await service.reorder(_USER, _HUMAN, SkillReorderRequest(skill_ids=[created.id, 999]))


async def test_a_malformed_identity_is_rejected() -> None:
    service, _, _, _ = _service()
    with pytest.raises(Unauthorized):
        await service.create("not-a-number", _HUMAN, build_skill_write())


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def __call__(self) -> datetime:
        return self._now
