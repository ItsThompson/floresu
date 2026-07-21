"""Unit tests for :class:`WorklogService`: the worklog lifecycle and tag rules.

Sociable: the real service runs over the in-memory repository and the real
write-event seam with a capturing consumer, so each test asserts the observable
outcome (the returned record, the active-list membership, the published event and
its actor/metadata) rather than internal calls. The content-hash re-embed gate is
exercised through the metadata the update event carries.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from floresu.core.actor import Actor, ActorType
from floresu.core.errors import Conflict, NotFound, Unauthorized, Validation
from floresu.core.events import REEMBED_CONTENT_HASH_KEY, WriteEvent
from floresu.worklog.injection import Clock
from floresu.worklog.service import WorklogService
from tests.worklog_fakes import (
    FakeSession,
    InMemoryWorklogRepository,
    build_worklog_write,
    capturing_publisher,
)

_USER = "1"
_HUMAN = Actor(type=ActorType.HUMAN)
_AGENT = Actor(type=ActorType.AGENT, label="claude")


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def __call__(self) -> datetime:
        return self._now


def _service(
    *, clock: Clock | None = None
) -> tuple[WorklogService, InMemoryWorklogRepository, FakeSession, list[WriteEvent]]:
    repo = InMemoryWorklogRepository()
    session = FakeSession()
    publisher, captured = capturing_publisher()
    kwargs = {"clock": clock} if clock is not None else {}
    service = WorklogService(session, repo, publisher, **kwargs)  # type: ignore[arg-type]
    return service, repo, session, captured


async def test_create_requires_only_title_and_date_and_defaults_the_rest() -> None:
    service, _, session, captured = _service()
    record = await service.create(_USER, _HUMAN, build_worklog_write(description=None, tags=[]))
    assert record.title == "Shipped the search API"
    assert record.description is None
    assert record.tags == []
    assert record.source_ids == []
    assert record.bullet_ids == []
    assert session.commits == 1
    # Attributed to the human, and the create carries the re-embed trigger.
    assert captured[-1].action.value == "create"
    assert captured[-1].actor.type is ActorType.HUMAN
    assert REEMBED_CONTENT_HASH_KEY in (captured[-1].metadata or {})


async def test_create_allows_zero_one_or_many_sources() -> None:
    service, repo, _, _ = _service()
    repo.own_source(1, 10)
    repo.own_source(1, 11)
    zero = await service.create(_USER, _HUMAN, build_worklog_write())
    one = await service.create(_USER, _HUMAN, build_worklog_write(source_ids=[10]))
    many = await service.create(_USER, _HUMAN, build_worklog_write(source_ids=[10, 11]))
    assert zero.source_ids == []
    assert one.source_ids == [10]
    assert many.source_ids == [10, 11]


async def test_duplicate_source_ids_are_deduplicated() -> None:
    service, repo, _, _ = _service()
    repo.own_source(1, 10)
    record = await service.create(_USER, _HUMAN, build_worklog_write(source_ids=[10, 10]))
    assert record.source_ids == [10]


async def test_create_rejects_a_source_the_user_does_not_own() -> None:
    service, repo, session, _ = _service()
    repo.own_source(1, 10)
    with pytest.raises(Validation):
        await service.create(_USER, _HUMAN, build_worklog_write(source_ids=[10, 999]))
    # Rejected before any write.
    assert session.commits == 0


async def test_agent_writes_carry_the_named_agent_actor() -> None:
    service, _, _, captured = _service()
    await service.create(_USER, _AGENT, build_worklog_write())
    assert captured[-1].actor.type is ActorType.AGENT
    assert captured[-1].actor.label == "claude"


async def test_a_new_label_creates_a_tag_and_an_existing_label_is_reused() -> None:
    service, _, _, _ = _service()
    await service.create(_USER, _HUMAN, build_worklog_write(tags=["python", "api"]))
    await service.create(_USER, _HUMAN, build_worklog_write(tags=["api", "search"]))
    tags = await service.list_tags(_USER)
    # "api" is reused, not duplicated: three distinct labels across two entries.
    assert sorted(tag.label for tag in tags) == ["api", "python", "search"]
    assert len({tag.id for tag in tags}) == 3


async def test_tags_are_trimmed_deduplicated_and_blanks_dropped() -> None:
    service, _, _, _ = _service()
    record = await service.create(
        _USER, _HUMAN, build_worklog_write(tags=[" api ", "api", "  ", "python"])
    )
    assert record.tags == ["api", "python"]


async def test_get_returns_the_record_with_edges_and_empty_bullets() -> None:
    service, repo, _, _ = _service()
    repo.own_source(1, 10)
    created = await service.create(
        _USER, _HUMAN, build_worklog_write(tags=["api"], source_ids=[10])
    )
    fetched = await service.get(_USER, created.id)
    assert fetched.tags == ["api"]
    assert fetched.source_ids == [10]
    assert fetched.bullet_ids == []


async def test_get_another_users_entry_is_not_found_no_existence_leak() -> None:
    service, _, _, _ = _service()
    mine = await service.create(_USER, _HUMAN, build_worklog_write())
    with pytest.raises(NotFound):
        await service.get("2", mine.id)


async def test_list_is_newest_first_and_active_only() -> None:
    service, _, _, _ = _service()
    older = await service.create(_USER, _HUMAN, build_worklog_write(entry_date="2026-01-01"))
    newer = await service.create(_USER, _HUMAN, build_worklog_write(entry_date="2026-02-01"))
    await service.archive(_USER, older.id, _HUMAN)
    active = await service.list_entries(_USER)
    assert [entry.id for entry in active] == [newer.id]
    including = await service.list_entries(_USER, include_archived=True)
    assert [entry.id for entry in including] == [newer.id, older.id]


async def test_edit_records_an_update_and_reembeds_on_content_change() -> None:
    service, _, _, captured = _service()
    created = await service.create(_USER, _HUMAN, build_worklog_write())
    await service.update(
        _USER,
        created.id,
        _HUMAN,
        build_worklog_write(description="A materially different summary."),
    )
    assert captured[-1].action.value == "update"
    # The content hash changed, so the event carries the re-embed trigger.
    assert REEMBED_CONTENT_HASH_KEY in (captured[-1].metadata or {})


async def test_edit_that_leaves_the_content_hash_unchanged_publishes_no_reembed() -> None:
    service, repo, _, captured = _service()
    repo.own_source(1, 10)
    created = await service.create(_USER, _HUMAN, build_worklog_write())
    # Same title + description; only tags and sources change -> hash unchanged.
    await service.update(
        _USER,
        created.id,
        _HUMAN,
        build_worklog_write(tags=["api"], source_ids=[10]),
    )
    assert captured[-1].action.value == "update"
    assert captured[-1].metadata is None


async def test_changing_only_the_date_does_not_reembed() -> None:
    service, _, _, captured = _service()
    created = await service.create(_USER, _HUMAN, build_worklog_write())
    await service.update(_USER, created.id, _HUMAN, build_worklog_write(entry_date="2026-03-03"))
    assert captured[-1].metadata is None


async def test_removing_a_tag_from_an_entry_leaves_the_tag_if_another_uses_it() -> None:
    service, _, _, _ = _service()
    first = await service.create(_USER, _HUMAN, build_worklog_write(tags=["api", "python"]))
    await service.create(_USER, _HUMAN, build_worklog_write(tags=["api"]))
    # Drop "api" from the first entry by omitting it from the full tag list.
    edited = await service.update(_USER, first.id, _HUMAN, build_worklog_write(tags=["python"]))
    assert edited.tags == ["python"]
    # The tag row survives because the second entry still uses it.
    assert "api" in [tag.label for tag in await service.list_tags(_USER)]


async def test_update_rejects_a_foreign_source() -> None:
    service, repo, _, _ = _service()
    repo.own_source(1, 10)
    created = await service.create(_USER, _HUMAN, build_worklog_write())
    with pytest.raises(Validation):
        await service.update(_USER, created.id, _HUMAN, build_worklog_write(source_ids=[999]))


async def test_archive_hides_from_active_reads_and_records_archive() -> None:
    clock = _FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    service, _, _, captured = _service(clock=clock)
    created = await service.create(_USER, _HUMAN, build_worklog_write())
    archived = await service.archive(_USER, created.id, _HUMAN)
    assert archived.archived_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert await service.list_entries(_USER) == []
    assert captured[-1].action.value == "archive"


async def test_double_archive_is_a_conflict() -> None:
    service, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_worklog_write())
    await service.archive(_USER, created.id, _HUMAN)
    with pytest.raises(Conflict):
        await service.archive(_USER, created.id, _HUMAN)


async def test_restore_returns_an_entry_and_records_restore() -> None:
    service, _, _, captured = _service()
    created = await service.create(_USER, _HUMAN, build_worklog_write())
    await service.archive(_USER, created.id, _HUMAN)
    restored = await service.restore(_USER, created.id, _HUMAN)
    assert restored.archived_at is None
    assert [entry.id for entry in await service.list_entries(_USER)] == [created.id]
    assert captured[-1].action.value == "restore"


async def test_restore_of_an_active_entry_is_a_conflict() -> None:
    service, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_worklog_write())
    with pytest.raises(Conflict):
        await service.restore(_USER, created.id, _HUMAN)


async def test_list_tags_is_scoped_to_the_user_and_ordered() -> None:
    service, _, _, _ = _service()
    await service.create(_USER, _HUMAN, build_worklog_write(tags=["zeta", "alpha"]))
    await service.create("2", _HUMAN, build_worklog_write(tags=["other"]))
    labels = [tag.label for tag in await service.list_tags(_USER)]
    assert labels == ["alpha", "zeta"]


async def test_a_malformed_identity_is_unauthorized() -> None:
    service, _, _, _ = _service()
    with pytest.raises(Unauthorized):
        await service.create("not-an-int", _HUMAN, build_worklog_write())


async def test_update_archive_restore_of_a_missing_entry_are_not_found() -> None:
    service, _, _, _ = _service()
    with pytest.raises(NotFound):
        await service.update(_USER, 9_999, _HUMAN, build_worklog_write())
    with pytest.raises(NotFound):
        await service.archive(_USER, 9_999, _HUMAN)
    with pytest.raises(NotFound):
        await service.restore(_USER, 9_999, _HUMAN)
