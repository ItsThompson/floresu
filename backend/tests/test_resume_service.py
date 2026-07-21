"""Unit tests for :class:`ResumeService`: the creation contract, items, revisions.

Sociable: the real service runs over the in-memory repository, a fake bullet-text
resolver, and the real write-event seam with a capturing consumer, so each test
asserts the observable outcome (the returned record, the published event, the
write-derived bullet-ref index, the appended revision snapshot) rather than
internal calls.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from floresu.core.actor import Actor, ActorType
from floresu.core.errors import Conflict, NotFound, Unauthorized, Validation
from floresu.core.events import WriteEvent
from floresu.resumes.document import LibraryRefItem, LocalItem
from floresu.resumes.models import ResumeKind, ResumeStatus
from floresu.resumes.schemas import ResumeReorderRequest
from floresu.resumes.service import ResumeService
from tests.resumes_fakes import (
    FakeSession,
    InMemoryBulletTextResolver,
    InMemoryResumeRepository,
    build_add_item,
    build_bullet_writer,
    build_create_request,
    build_section,
    build_update,
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


class _SeqIds:
    def __init__(self) -> None:
        self._n = 0

    def __call__(self) -> str:
        self._n += 1
        return f"item-{self._n}"


def _service() -> tuple[
    ResumeService,
    InMemoryResumeRepository,
    InMemoryBulletTextResolver,
    FakeSession,
    list[WriteEvent],
]:
    repo = InMemoryResumeRepository()
    resolver = InMemoryBulletTextResolver()
    session = FakeSession()
    publisher, captured = capturing_publisher()
    service = ResumeService(
        session,  # type: ignore[arg-type]
        repo,
        resolver,
        publisher,
        build_bullet_writer(session, publisher),  # type: ignore[arg-type]
        clock=_FixedClock(datetime(2026, 1, 1, tzinfo=UTC)),
        id_factory=_SeqIds(),
    )
    return service, repo, resolver, session, captured


def _ref_section(section_id: str, item_id: str, bullet_id: int) -> dict[str, Any]:
    return build_section(
        id=section_id,
        item_order=[item_id],
        items={item_id: {"id": item_id, "kind": "library_ref", "bullet_id": bullet_id}},
    )


async def _seed_source_with_ref(
    service: ResumeService,
    resolver: InMemoryBulletTextResolver,
    *,
    kind: str = "living",
    job_application_id: int | None = None,
) -> int:
    """Create a source resume that references canonical bullet 10, and return its id."""
    resolver.own_bullet(1, 10, "Cut latency 40%.")
    created = await service.create(
        _USER, _HUMAN, build_create_request(kind=kind, job_application_id=job_application_id)
    )
    updated = await service.update(
        _USER,
        created.id,
        _HUMAN,
        created.revision,
        build_update(sections=[_ref_section("sec-work", "a", 10)]),
    )
    return updated.id


# --- creation contract -------------------------------------------------------


async def test_create_living_blank_is_a_draft_at_revision_one() -> None:
    service, repo, _, session, captured = _service()
    record = await service.create(_USER, _HUMAN, build_create_request())
    assert record.kind is ResumeKind.LIVING
    assert record.status is ResumeStatus.DRAFT
    assert record.revision == 1
    assert record.forked_from_resume_id is None
    assert record.document.schema_version == 1
    assert session.commits == 1
    # The create appends revision snapshot number 1 and publishes a create event.
    assert repo.revision(record.id, 1) is not None
    assert captured[-1].action.value == "create"
    assert captured[-1].actor.type is ActorType.HUMAN
    assert captured[-1].metadata == {"revision": 1}


async def test_create_application_requires_a_job_application() -> None:
    service, _, _, session, _ = _service()
    with pytest.raises(Validation):
        await service.create(_USER, _HUMAN, build_create_request(kind="application"))
    assert session.commits == 0


async def test_create_living_rejects_a_job_application() -> None:
    service, _, _, _, _ = _service()
    with pytest.raises(Validation):
        await service.create(_USER, _HUMAN, build_create_request(job_application_id=7))


async def test_create_application_links_the_job_application_one_to_one() -> None:
    service, repo, _, _, _ = _service()
    repo.own_job_application(1, 7)
    record = await service.create(
        _USER, _HUMAN, build_create_request(kind="application", job_application_id=7)
    )
    assert record.kind is ResumeKind.APPLICATION
    assert record.status is ResumeStatus.DRAFT
    assert record.job_application_id == 7


async def test_create_application_rejects_a_foreign_job_application() -> None:
    service, _, _, _, _ = _service()
    with pytest.raises(Validation):
        await service.create(
            _USER, _HUMAN, build_create_request(kind="application", job_application_id=7)
        )


async def test_create_application_rejects_an_already_linked_job_application() -> None:
    service, repo, _, _, _ = _service()
    repo.own_job_application(1, 7)
    await service.create(
        _USER, _HUMAN, build_create_request(kind="application", job_application_id=7)
    )
    with pytest.raises(Conflict):
        await service.create(
            _USER, _HUMAN, build_create_request(kind="application", job_application_id=7)
        )


async def test_from_resume_seeds_content_and_records_the_fork() -> None:
    service, _, resolver, _, _ = _service()
    source = await _seed_source_with_ref(service, resolver)
    seeded = await service.create(
        _USER,
        _HUMAN,
        build_create_request(source={"mode": "from_resume", "from_resume_id": source}),
    )
    assert seeded.forked_from_resume_id == source
    assert seeded.kind is ResumeKind.LIVING
    # The seeded document copies the source's referencing item.
    assert any(
        isinstance(item, LibraryRefItem)
        for section in seeded.document.sections
        for item in section.items.values()
    )


async def test_duplicate_is_a_faithful_copy_and_records_the_fork() -> None:
    service, _, resolver, _, _ = _service()
    source_id = await _seed_source_with_ref(service, resolver)
    duplicate = await service.create(
        _USER, _HUMAN, build_create_request(source={"mode": "duplicate", "duplicate_id": source_id})
    )
    assert duplicate.forked_from_resume_id == source_id
    original = await service.get(_USER, source_id)
    assert duplicate.document.sections[0].items == original.document.sections[0].items


async def test_result_kind_is_set_by_kind_never_inferred_from_source() -> None:
    service, repo, resolver, _, _ = _service()
    repo.own_job_application(1, 7)
    application_id = await _seed_source_with_ref(
        service, resolver, kind="application", job_application_id=7
    )
    # Duplicate an application resume but ask for a living result: kind wins.
    living = await service.create(
        _USER,
        _HUMAN,
        build_create_request(
            kind="living", source={"mode": "duplicate", "duplicate_id": application_id}
        ),
    )
    assert living.kind is ResumeKind.LIVING


async def test_seed_from_a_missing_source_is_rejected() -> None:
    service, _, _, _, _ = _service()
    with pytest.raises(Validation):
        await service.create(
            _USER,
            _HUMAN,
            build_create_request(source={"mode": "from_resume", "from_resume_id": 999}),
        )


# --- reads -------------------------------------------------------------------


async def test_get_another_users_resume_is_not_found() -> None:
    service, _, _, _, _ = _service()
    mine = await service.create(_USER, _HUMAN, build_create_request())
    with pytest.raises(NotFound):
        await service.get("2", mine.id)


async def test_list_is_newest_first_and_filters_by_kind() -> None:
    service, repo, _, _, _ = _service()
    repo.own_job_application(1, 7)
    living = await service.create(_USER, _HUMAN, build_create_request())
    application = await service.create(
        _USER, _HUMAN, build_create_request(kind="application", job_application_id=7)
    )
    listed = await service.list_resumes(_USER)
    assert [row.id for row in listed] == [application.id, living.id]
    only_living = await service.list_resumes(_USER, kind=ResumeKind.LIVING)
    assert [row.id for row in only_living] == [living.id]


async def test_malformed_identity_is_unauthorized() -> None:
    service, _, _, _, _ = _service()
    with pytest.raises(Unauthorized):
        await service.create("not-an-int", _HUMAN, build_create_request())


# --- items -------------------------------------------------------------------


async def test_add_item_appends_to_the_id_keyed_map_and_order() -> None:
    service, _, _, _, captured = _service()
    created = await service.create(_USER, _HUMAN, build_create_request())
    with_section = await service.update(
        _USER, created.id, _HUMAN, created.revision, build_update(sections=[build_section()])
    )
    record = await service.add_item(
        _USER, with_section.id, _HUMAN, with_section.revision, build_add_item()
    )
    section = record.document.sections[0]
    assert section.item_order == ["item-1"]
    assert isinstance(section.items["item-1"], LocalItem)
    assert record.revision == with_section.revision + 1
    assert captured[-1].action.value == "update"


async def test_add_library_ref_item_indexes_the_bullet_ref() -> None:
    service, repo, resolver, _, _ = _service()
    resolver.own_bullet(1, 10, "Cut latency 40%.")
    created = await service.create(_USER, _HUMAN, build_create_request())
    with_section = await service.update(
        _USER, created.id, _HUMAN, created.revision, build_update(sections=[build_section()])
    )
    await service.add_item(
        _USER,
        with_section.id,
        _HUMAN,
        with_section.revision,
        build_add_item(item={"kind": "library_ref", "bullet_id": 10}),
    )
    assert repo.bullet_refs(with_section.id) == [10]
    assert await service.bullet_used_in_count(_USER, 10) == 1


async def test_add_item_to_an_unknown_section_is_rejected() -> None:
    service, _, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_create_request())
    with pytest.raises(Validation):
        await service.add_item(
            _USER, created.id, _HUMAN, created.revision, build_add_item(section_id="nope")
        )


async def test_add_item_referencing_a_foreign_bullet_is_rejected() -> None:
    service, _, _, session, _ = _service()
    created = await service.create(_USER, _HUMAN, build_create_request())
    with_section = await service.update(
        _USER, created.id, _HUMAN, created.revision, build_update(sections=[build_section()])
    )
    commits_before = session.commits
    with pytest.raises(Validation):
        await service.add_item(
            _USER,
            with_section.id,
            _HUMAN,
            with_section.revision,
            build_add_item(item={"kind": "library_ref", "bullet_id": 999}),
        )
    # The rejected write did not commit.
    assert session.commits == commits_before


async def test_remove_item_drops_it_from_the_map_and_order() -> None:
    service, _, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_create_request())
    section = build_section(
        item_order=["a", "b"],
        items={
            "a": {"id": "a", "kind": "local", "text": "one"},
            "b": {"id": "b", "kind": "local", "text": "two"},
        },
    )
    with_items = await service.update(
        _USER, created.id, _HUMAN, created.revision, build_update(sections=[section])
    )
    record = await service.remove_item(_USER, with_items.id, _HUMAN, with_items.revision, "a")
    remaining = record.document.sections[0]
    assert remaining.item_order == ["b"]
    assert "a" not in remaining.items


async def test_remove_a_missing_item_is_not_found() -> None:
    service, _, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_create_request())
    with pytest.raises(NotFound):
        await service.remove_item(_USER, created.id, _HUMAN, created.revision, "ghost")


# --- reorder -----------------------------------------------------------------


async def test_reorder_items_permutes_by_id_and_records_a_reorder() -> None:
    service, _, _, _, captured = _service()
    created = await service.create(_USER, _HUMAN, build_create_request())
    section = build_section(
        item_order=["a", "b"],
        items={
            "a": {"id": "a", "kind": "local", "text": "one"},
            "b": {"id": "b", "kind": "local", "text": "two"},
        },
    )
    with_items = await service.update(
        _USER, created.id, _HUMAN, created.revision, build_update(sections=[section])
    )
    record = await service.reorder(
        _USER,
        with_items.id,
        _HUMAN,
        with_items.revision,
        ResumeReorderRequest(item_orders={"sec-work": ["b", "a"]}),
    )
    assert record.document.sections[0].item_order == ["b", "a"]
    assert captured[-1].action.value == "reorder"
    assert captured[-1].metadata is not None
    assert captured[-1].metadata["item_orders"] == {"sec-work": ["b", "a"]}


async def test_reorder_sections_permutes_section_order() -> None:
    service, _, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_create_request())
    sections = [
        build_section(id="s1", title="A"),
        build_section(id="s2", kind="projects", title="B"),
    ]
    with_sections = await service.update(
        _USER, created.id, _HUMAN, created.revision, build_update(sections=sections)
    )
    record = await service.reorder(
        _USER,
        with_sections.id,
        _HUMAN,
        with_sections.revision,
        ResumeReorderRequest(section_order=["s2", "s1"]),
    )
    assert [section.id for section in record.document.sections] == ["s2", "s1"]


async def test_a_partial_or_colliding_reorder_is_rejected() -> None:
    service, _, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_create_request())
    section = build_section(
        item_order=["a", "b"],
        items={
            "a": {"id": "a", "kind": "local", "text": "one"},
            "b": {"id": "b", "kind": "local", "text": "two"},
        },
    )
    with_items = await service.update(
        _USER, created.id, _HUMAN, created.revision, build_update(sections=[section])
    )
    with pytest.raises(Validation):
        # Partial: 'b' is missing.
        await service.reorder(
            _USER,
            with_items.id,
            _HUMAN,
            with_items.revision,
            ResumeReorderRequest(item_orders={"sec-work": ["a"]}),
        )
    with pytest.raises(Validation):
        # Collision: 'a' twice.
        await service.reorder(
            _USER,
            with_items.id,
            _HUMAN,
            with_items.revision,
            ResumeReorderRequest(item_orders={"sec-work": ["a", "a"]}),
        )


async def test_a_partial_or_colliding_section_reorder_is_rejected() -> None:
    service, _, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_create_request())
    sections = [
        build_section(id="s1", title="A"),
        build_section(id="s2", kind="projects", title="B"),
    ]
    with_sections = await service.update(
        _USER, created.id, _HUMAN, created.revision, build_update(sections=sections)
    )
    with pytest.raises(Validation):
        # Partial: 's2' is missing.
        await service.reorder(
            _USER,
            with_sections.id,
            _HUMAN,
            with_sections.revision,
            ResumeReorderRequest(section_order=["s1"]),
        )
    with pytest.raises(Validation):
        # Collision: 's1' twice.
        await service.reorder(
            _USER,
            with_sections.id,
            _HUMAN,
            with_sections.revision,
            ResumeReorderRequest(section_order=["s1", "s1"]),
        )


def test_a_reorder_request_requires_at_least_one_dimension() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ResumeReorderRequest()


# --- optimistic concurrency & revisions --------------------------------------


async def test_a_stale_write_is_rejected_and_not_applied() -> None:
    service, _, _, session, _ = _service()
    created = await service.create(_USER, _HUMAN, build_create_request())
    # Someone else already advanced the revision to 2.
    await service.update(_USER, created.id, _HUMAN, created.revision, build_update(title="First"))
    commits_before = session.commits
    with pytest.raises(Conflict):
        # A stale If-Match (still 1) must be rejected, not silently overwrite.
        await service.update(_USER, created.id, _HUMAN, 1, build_update(title="Stale"))
    assert session.commits == commits_before
    assert (await service.get(_USER, created.id)).title == "First"


async def test_a_successful_write_increments_revision_and_appends_a_snapshot() -> None:
    service, repo, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_create_request())
    updated = await service.update(
        _USER, created.id, _HUMAN, created.revision, build_update(title="Renamed")
    )
    assert updated.revision == 2
    assert repo.revision_count(created.id) == 2
    assert repo.revision(created.id, 2) is not None


async def test_a_revision_snapshot_is_immune_to_a_later_library_edit() -> None:
    service, repo, resolver, _, _ = _service()
    resolver.own_bullet(1, 10, "Original framing.")
    created = await service.create(_USER, _HUMAN, build_create_request())
    with_ref = await service.update(
        _USER,
        created.id,
        _HUMAN,
        created.revision,
        build_update(sections=[_ref_section("sec-work", "a", 10)]),
    )
    # The library bullet is edited after the snapshot was taken.
    resolver.own_bullet(1, 10, "Edited framing.")
    await service.update(
        _USER,
        with_ref.id,
        _HUMAN,
        with_ref.revision,
        build_update(sections=[_ref_section("sec-work", "a", 10)]),
    )
    snapshot_two = repo.revision(created.id, 2)
    snapshot_three = repo.revision(created.id, 3)
    assert snapshot_two is not None
    assert snapshot_three is not None
    # The earlier snapshot keeps the text as it was resolved at that moment.
    assert snapshot_two.document["sections"][0]["items"]["a"]["text"] == "Original framing."
    assert snapshot_three.document["sections"][0]["items"]["a"]["text"] == "Edited framing."


async def test_bullet_ref_is_reindexed_on_every_save_and_used_in_count_tracks_it() -> None:
    service, repo, resolver, _, _ = _service()
    resolver.own_bullet(1, 10, "framing")
    created = await service.create(_USER, _HUMAN, build_create_request())
    with_ref = await service.update(
        _USER,
        created.id,
        _HUMAN,
        created.revision,
        build_update(sections=[_ref_section("sec-work", "a", 10)]),
    )
    assert repo.bullet_refs(created.id) == [10]
    assert await service.bullet_used_in_count(_USER, 10) == 1
    # Dropping the referencing item reindexes to empty; the count follows.
    await service.update(_USER, with_ref.id, _HUMAN, with_ref.revision, build_update(sections=[]))
    assert repo.bullet_refs(created.id) == []
    assert await service.bullet_used_in_count(_USER, 10) == 0


async def test_used_in_count_counts_every_referencing_resume() -> None:
    service, _, resolver, _, _ = _service()
    resolver.own_bullet(1, 10, "shared framing")
    for _ in range(2):
        created = await service.create(_USER, _HUMAN, build_create_request())
        await service.update(
            _USER,
            created.id,
            _HUMAN,
            created.revision,
            build_update(sections=[_ref_section("sec-work", "a", 10)]),
        )
    assert await service.bullet_used_in_count(_USER, 10) == 2


# --- guards ------------------------------------------------------------------


async def test_a_finalized_resume_is_read_only() -> None:
    service, repo, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_create_request())
    # Simulate the finalize routine (built elsewhere) freezing the resume.
    stored = await repo.get(1, created.id)
    assert stored is not None
    stored.status = ResumeStatus.FINALIZED
    with pytest.raises(Conflict):
        await service.update(_USER, created.id, _HUMAN, created.revision, build_update())


async def test_agent_writes_carry_the_named_agent_actor() -> None:
    service, _, _, _, captured = _service()
    await service.create(_USER, _AGENT, build_create_request())
    assert captured[-1].actor.type is ActorType.AGENT
    assert captured[-1].actor.label == "claude"
