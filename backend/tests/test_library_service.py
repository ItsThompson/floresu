"""Unit tests for :class:`LibraryService`: the bulletpoint lifecycle and edges.

Sociable: the real service runs over the in-memory repository and the real
write-event seam with a capturing consumer, so each test asserts the observable
outcome (the returned record, the active-list membership, the published event and
its actor/metadata) rather than internal calls. The content-hash re-embed gate is
exercised through the metadata the create/update event carries.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from floresu.core.actor import Actor, ActorType
from floresu.core.errors import Conflict, NotFound, Unauthorized, Validation
from floresu.core.events import REEMBED_CONTENT_HASH_KEY, WriteEvent
from floresu.library.injection import Clock
from floresu.library.service import LibraryService
from tests.library_fakes import (
    FakeSession,
    InMemoryBulletUsageCounter,
    InMemoryLibraryRepository,
    build_bullet_write,
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
    *, clock: Clock | None = None, usage: InMemoryBulletUsageCounter | None = None
) -> tuple[LibraryService, InMemoryLibraryRepository, FakeSession, list[WriteEvent]]:
    repo = InMemoryLibraryRepository()
    session = FakeSession()
    publisher, captured = capturing_publisher()
    counter = usage if usage is not None else InMemoryBulletUsageCounter()
    kwargs = {"clock": clock} if clock is not None else {}
    service = LibraryService(session, repo, publisher, counter, **kwargs)  # type: ignore[arg-type]
    return service, repo, session, captured


async def test_create_persists_text_with_source_and_worklog_edges() -> None:
    service, repo, session, captured = _service()
    repo.own_source(1, 100)
    repo.own_worklog(1, 10)
    record = await service.create(
        _USER, _HUMAN, build_bullet_write(source_ids=[100], worklog_ids=[10])
    )
    assert record.text.startswith("Cut p99 checkout latency")
    assert record.source_ids == [100]
    assert record.worklog_ids == [10]
    assert record.revision == 1
    assert record.used_in_count == 0
    assert session.commits == 1
    # Attributed to the human, and the create carries the re-embed trigger.
    assert captured[-1].action.value == "create"
    assert captured[-1].actor.type is ActorType.HUMAN
    assert REEMBED_CONTENT_HASH_KEY in (captured[-1].metadata or {})


async def test_a_bullet_may_link_one_or_many_sources_and_worklogs() -> None:
    service, repo, _, _ = _service()
    for source_id in (100, 101):
        repo.own_source(1, source_id)
    for worklog_id in (10, 11):
        repo.own_worklog(1, worklog_id)
    record = await service.create(
        _USER, _HUMAN, build_bullet_write(source_ids=[100, 101], worklog_ids=[10, 11])
    )
    assert record.source_ids == [100, 101]
    assert record.worklog_ids == [10, 11]


async def test_a_bullet_with_both_edges_empty_is_allowed_but_ungrouped() -> None:
    service, _, session, _ = _service()
    record = await service.create(_USER, _HUMAN, build_bullet_write())
    assert record.source_ids == []
    assert record.worklog_ids == []
    assert session.commits == 1


async def test_duplicate_edge_ids_are_deduplicated() -> None:
    service, repo, _, _ = _service()
    repo.own_source(1, 100)
    repo.own_worklog(1, 10)
    record = await service.create(
        _USER, _HUMAN, build_bullet_write(source_ids=[100, 100], worklog_ids=[10, 10])
    )
    assert record.source_ids == [100]
    assert record.worklog_ids == [10]


async def test_create_rejects_a_source_the_user_does_not_own() -> None:
    service, repo, session, _ = _service()
    repo.own_source(1, 100)
    with pytest.raises(Validation):
        await service.create(_USER, _HUMAN, build_bullet_write(source_ids=[100, 999]))
    assert session.commits == 0


async def test_create_rejects_a_worklog_the_user_does_not_own() -> None:
    service, repo, session, _ = _service()
    repo.own_worklog(1, 10)
    with pytest.raises(Validation):
        await service.create(_USER, _HUMAN, build_bullet_write(worklog_ids=[10, 999]))
    assert session.commits == 0


async def test_agent_writes_carry_the_named_agent_actor() -> None:
    service, _, _, captured = _service()
    await service.create(_USER, _AGENT, build_bullet_write())
    assert captured[-1].actor.type is ActorType.AGENT
    assert captured[-1].actor.label == "claude"


async def test_long_bullet_text_is_truncated_in_the_audit_summary() -> None:
    service, _, _, captured = _service()
    long_text = "Led " + "a cross-functional migration " * 10
    await service.create(_USER, _HUMAN, build_bullet_write(text=long_text))
    summary = captured[-1].summary or ""
    # The audit line stays short: the long text is collapsed and ellipsized.
    assert summary.endswith("\u2026\u201d")
    assert len(summary) < len(long_text)


async def test_get_returns_the_record_with_its_edges() -> None:
    service, repo, _, _ = _service()
    repo.own_source(1, 100)
    repo.own_worklog(1, 10)
    created = await service.create(
        _USER, _HUMAN, build_bullet_write(source_ids=[100], worklog_ids=[10])
    )
    fetched = await service.get(_USER, created.id)
    assert fetched.source_ids == [100]
    assert fetched.worklog_ids == [10]


async def test_get_another_users_bullet_is_not_found_no_existence_leak() -> None:
    service, _, _, _ = _service()
    mine = await service.create(_USER, _HUMAN, build_bullet_write())
    with pytest.raises(NotFound):
        await service.get("2", mine.id)


async def test_list_reports_the_real_used_in_count_per_bullet() -> None:
    counter = InMemoryBulletUsageCounter()
    service, _, _, _ = _service(usage=counter)
    shared = await service.create(_USER, _HUMAN, build_bullet_write(text="Shared bullet."))
    once = await service.create(_USER, _HUMAN, build_bullet_write(text="Used once."))
    unused = await service.create(_USER, _HUMAN, build_bullet_write(text="Unused bullet."))
    counter.set_count(shared.id, 3)
    counter.set_count(once.id, 1)
    # `unused` is left unseeded: absent from the grouped result, defaults to 0.
    by_id = {record.id: record.used_in_count for record in await service.list_bullets(_USER)}
    assert by_id == {shared.id: 3, once.id: 1, unused.id: 0}


async def test_list_issues_one_batched_count_for_the_page() -> None:
    counter = InMemoryBulletUsageCounter()
    service, _, _, _ = _service(usage=counter)
    first = await service.create(_USER, _HUMAN, build_bullet_write(text="First."))
    second = await service.create(_USER, _HUMAN, build_bullet_write(text="Second."))
    await service.list_bullets(_USER)
    # Exactly one grouped count call carrying every id on the page: no per-bullet N+1.
    assert counter.calls == [[second.id, first.id]]


async def test_empty_library_list_counts_with_no_query_error() -> None:
    counter = InMemoryBulletUsageCounter()
    service, _, _, _ = _service(usage=counter)
    assert await service.list_bullets(_USER) == []
    assert counter.calls == [[]]


async def test_get_reports_the_real_used_in_count() -> None:
    counter = InMemoryBulletUsageCounter()
    service, _, _, _ = _service(usage=counter)
    created = await service.create(_USER, _HUMAN, build_bullet_write())
    counter.set_count(created.id, 2)
    assert (await service.get(_USER, created.id)).used_in_count == 2


async def test_list_is_newest_first_and_active_only() -> None:
    service, _, _, _ = _service()
    older = await service.create(_USER, _HUMAN, build_bullet_write(text="Older bullet."))
    newer = await service.create(_USER, _HUMAN, build_bullet_write(text="Newer bullet."))
    await service.archive(_USER, older.id, _HUMAN)
    active = await service.list_bullets(_USER)
    assert [bullet.id for bullet in active] == [newer.id]
    including = await service.list_bullets(_USER, include_archived=True)
    assert [bullet.id for bullet in including] == [newer.id, older.id]


async def test_edit_records_an_update_and_reembeds_on_text_change() -> None:
    service, _, _, captured = _service()
    created = await service.create(_USER, _HUMAN, build_bullet_write())
    await service.update(
        _USER,
        created.id,
        _HUMAN,
        build_bullet_write(text="A materially different framing."),
        created.revision,
    )
    assert captured[-1].action.value == "update"
    assert REEMBED_CONTENT_HASH_KEY in (captured[-1].metadata or {})


async def test_edit_that_leaves_the_text_unchanged_publishes_no_reembed() -> None:
    service, repo, _, captured = _service()
    repo.own_source(1, 100)
    created = await service.create(_USER, _HUMAN, build_bullet_write())
    # Same text; only the source edges change -> hash unchanged, no re-embed. The
    # CAS still runs, so the token advances (any successful write bumps it).
    edited = await service.update(
        _USER, created.id, _HUMAN, build_bullet_write(source_ids=[100]), created.revision
    )
    assert captured[-1].action.value == "update"
    assert captured[-1].metadata is None
    assert edited.revision == created.revision + 1


async def test_edit_reframes_the_edges() -> None:
    service, repo, _, _ = _service()
    repo.own_source(1, 100)
    repo.own_worklog(1, 10)
    repo.own_worklog(1, 11)
    created = await service.create(_USER, _HUMAN, build_bullet_write(worklog_ids=[10]))
    edited = await service.update(
        _USER,
        created.id,
        _HUMAN,
        build_bullet_write(source_ids=[100], worklog_ids=[11]),
        created.revision,
    )
    assert edited.source_ids == [100]
    assert edited.worklog_ids == [11]


async def test_edit_advances_the_revision_token_by_one() -> None:
    service, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_bullet_write())
    edited = await service.update(
        _USER, created.id, _HUMAN, build_bullet_write(text="Reworded."), created.revision
    )
    # The CAS advances the optimistic token by exactly one on a successful write.
    assert created.revision == 1
    assert edited.revision == 2


async def test_a_stale_if_match_is_a_recoverable_conflict_and_no_overwrite() -> None:
    service, _, _, captured = _service()
    created = await service.create(_USER, _HUMAN, build_bullet_write())
    # Advance the token once, so the originally-loaded revision is now stale.
    await service.update(
        _USER, created.id, _HUMAN, build_bullet_write(text="First edit."), created.revision
    )
    events_before = len(captured)
    with pytest.raises(Conflict):
        await service.update(
            _USER, created.id, _HUMAN, build_bullet_write(text="Stale edit."), created.revision
        )
    # The stale write published nothing and did not overwrite the current text.
    assert len(captured) == events_before
    current = await service.get(_USER, created.id)
    assert current.text == "First edit."
    assert current.revision == 2


async def test_update_rejects_a_foreign_source() -> None:
    service, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_bullet_write())
    with pytest.raises(Validation):
        await service.update(
            _USER, created.id, _HUMAN, build_bullet_write(source_ids=[999]), created.revision
        )


async def test_archive_hides_from_active_reads_and_records_archive() -> None:
    clock = _FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    service, _, _, captured = _service(clock=clock)
    created = await service.create(_USER, _HUMAN, build_bullet_write())
    archived = await service.archive(_USER, created.id, _HUMAN)
    assert archived.archived_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert await service.list_bullets(_USER) == []
    assert captured[-1].action.value == "archive"


async def test_double_archive_is_a_conflict() -> None:
    service, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_bullet_write())
    await service.archive(_USER, created.id, _HUMAN)
    with pytest.raises(Conflict):
        await service.archive(_USER, created.id, _HUMAN)


async def test_restore_returns_a_bullet_and_records_restore() -> None:
    service, _, _, captured = _service()
    created = await service.create(_USER, _HUMAN, build_bullet_write())
    await service.archive(_USER, created.id, _HUMAN)
    restored = await service.restore(_USER, created.id, _HUMAN)
    assert restored.archived_at is None
    assert [bullet.id for bullet in await service.list_bullets(_USER)] == [created.id]
    assert captured[-1].action.value == "restore"


async def test_restore_of_an_active_bullet_is_a_conflict() -> None:
    service, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_bullet_write())
    with pytest.raises(Conflict):
        await service.restore(_USER, created.id, _HUMAN)


async def test_a_malformed_identity_is_unauthorized() -> None:
    service, _, _, _ = _service()
    with pytest.raises(Unauthorized):
        await service.create("not-an-int", _HUMAN, build_bullet_write())


async def test_update_archive_restore_of_a_missing_bullet_are_not_found() -> None:
    service, _, _, _ = _service()
    with pytest.raises(NotFound):
        await service.update(_USER, 9_999, _HUMAN, build_bullet_write(), 1)
    with pytest.raises(NotFound):
        await service.archive(_USER, 9_999, _HUMAN)
    with pytest.raises(NotFound):
        await service.restore(_USER, 9_999, _HUMAN)
