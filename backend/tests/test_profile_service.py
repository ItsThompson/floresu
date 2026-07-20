"""SourceService business rules, through its public methods with an in-memory
repository, the real write-event seam (capturing consumer), and a fake session
recording the transaction boundary (sociable)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from floresu.core.actor import Actor, ActorType
from floresu.core.errors import Conflict, NotFound, Unauthorized, Validation
from floresu.core.events import Action, WriteEvent
from floresu.profile.injection import Clock
from floresu.profile.models import SourceKind
from floresu.profile.schemas import (
    CertificationDetail,
    EducationDetail,
    ProjectDetail,
    RoleDetail,
)
from floresu.profile.service import SourceService
from tests.profile_fakes import (
    FakeSession,
    InMemorySourceRepository,
    build_certification_write,
    build_education_write,
    build_project_write,
    build_role_write,
    capturing_publisher,
)

_USER = "1"
_HUMAN = Actor(type=ActorType.HUMAN)
_AGENT = Actor(type=ActorType.AGENT, label="claude")


def _service(
    *, clock: Clock | None = None
) -> tuple[SourceService, InMemorySourceRepository, FakeSession, list[WriteEvent]]:
    repo = InMemorySourceRepository()
    session = FakeSession()
    publisher, captured = capturing_publisher()
    kwargs = {"clock": clock} if clock is not None else {}
    service = SourceService(session, repo, publisher, **kwargs)  # type: ignore[arg-type]
    return service, repo, session, captured


async def test_create_role_writes_base_and_subtype_and_publishes_create() -> None:
    service, _, session, captured = _service()
    record = await service.create(_USER, _HUMAN, build_role_write())

    assert record.id >= 1
    assert record.kind is SourceKind.ROLE
    assert record.display_label == "Senior Engineer, Acme"
    assert record.date_start == date(2020, 1, 1)
    assert record.sort_order == 0
    assert record.archived_at is None
    assert isinstance(record.detail, RoleDetail)
    assert record.detail.company == "Acme"
    assert record.detail.job_title == "Senior Engineer"
    assert record.detail.title_aliases == ["Sr. SWE"]
    assert record.detail.location == "Remote"

    # Exactly one create event, attributed to the human, for this source.
    assert len(captured) == 1
    event = captured[0]
    assert event.action is Action.CREATE
    assert event.entity_type == "source"
    assert event.entity_id == record.id
    assert event.user_id == 1
    assert event.actor == _HUMAN
    assert event.summary is not None and "role" in event.summary
    assert session.commits == 1


async def test_an_open_ended_role_stores_a_null_date_end() -> None:
    service, _, _, _ = _service()
    record = await service.create(_USER, _HUMAN, build_role_write(date_end=None))
    assert record.date_end is None


async def test_create_project_certification_education_persist_kind_fields() -> None:
    service, _, _, _ = _service()

    project = await service.create(_USER, _HUMAN, build_project_write())
    assert isinstance(project.detail, ProjectDetail)
    assert project.detail.links == ["https://example.com/floresu"]

    cert = await service.create(_USER, _HUMAN, build_certification_write())
    assert isinstance(cert.detail, CertificationDetail)
    assert cert.detail.issuer == "Amazon Web Services"
    assert cert.detail.credential_id == "ABC-123"
    assert cert.date_start == date(2023, 6, 1)

    education = await service.create(_USER, _HUMAN, build_education_write())
    assert isinstance(education.detail, EducationDetail)
    assert education.detail.institution == "State University"
    assert education.detail.degree == "BSc"
    assert education.detail.field == "Computer Science"

    # Each created item is a distinct, attachable source (its own id + kind).
    ids = {project.id, cert.id, education.id}
    assert len(ids) == 3


async def test_agent_writes_carry_the_named_agent_actor() -> None:
    service, _, _, captured = _service()
    await service.create(_USER, _AGENT, build_role_write())
    assert captured[0].actor == _AGENT
    assert captured[0].actor.label == "claude"


async def test_get_returns_typed_detail_for_the_owner() -> None:
    service, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_certification_write())
    fetched = await service.get(_USER, created.id)
    assert fetched.id == created.id
    assert isinstance(fetched.detail, CertificationDetail)
    assert fetched.detail.issuer == "Amazon Web Services"


async def test_get_missing_source_is_not_found() -> None:
    service, _, _, _ = _service()
    with pytest.raises(NotFound):
        await service.get(_USER, 999)


async def test_update_archive_restore_of_a_missing_source_are_not_found() -> None:
    service, _, _, _ = _service()
    with pytest.raises(NotFound):
        await service.update(_USER, 999, _HUMAN, build_role_write())
    with pytest.raises(NotFound):
        await service.archive(_USER, 999, _HUMAN)
    with pytest.raises(NotFound):
        await service.restore(_USER, 999, _HUMAN)


async def test_get_another_users_source_is_not_found_no_existence_leak() -> None:
    service, _, _, _ = _service()
    mine = await service.create(_USER, _HUMAN, build_role_write())
    # A different account cannot read it; the miss is a 404, not a 403.
    with pytest.raises(NotFound):
        await service.get("2", mine.id)


async def test_edit_any_field_records_an_update() -> None:
    service, _, session, captured = _service()
    created = await service.create(_USER, _HUMAN, build_role_write())
    captured.clear()

    edited = await service.update(
        _USER,
        created.id,
        _HUMAN,
        build_role_write(job_title="Staff Engineer", display_label="Staff Engineer, Acme"),
    )
    assert isinstance(edited.detail, RoleDetail)
    assert edited.detail.job_title == "Staff Engineer"
    assert edited.display_label == "Staff Engineer, Acme"
    assert len(captured) == 1
    assert captured[0].action is Action.UPDATE
    assert captured[0].entity_id == created.id
    assert session.commits == 2  # create + update


async def test_edit_cannot_change_kind() -> None:
    service, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_role_write())
    with pytest.raises(Validation) as excinfo:
        await service.update(_USER, created.id, _HUMAN, build_project_write())
    assert excinfo.value.fields is not None
    assert "kind" in excinfo.value.fields


async def test_archive_sets_archived_at_records_archive_and_leaves_active_lists() -> None:
    clock = _FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    service, _, _, captured = _service(clock=clock)
    created = await service.create(_USER, _HUMAN, build_role_write())
    captured.clear()

    archived = await service.archive(_USER, created.id, _HUMAN)
    assert archived.archived_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert captured[0].action is Action.ARCHIVE

    # Removed from the active list, but visible with include_archived.
    active = await service.list_sources(_USER)
    assert active == []
    including = await service.list_sources(_USER, include_archived=True)
    assert [s.id for s in including] == [created.id]


async def test_double_archive_is_a_conflict() -> None:
    service, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_role_write())
    await service.archive(_USER, created.id, _HUMAN)
    with pytest.raises(Conflict):
        await service.archive(_USER, created.id, _HUMAN)


async def test_restore_clears_archive_and_records_restore() -> None:
    service, _, _, captured = _service()
    created = await service.create(_USER, _HUMAN, build_role_write())
    await service.archive(_USER, created.id, _HUMAN)
    captured.clear()

    restored = await service.restore(_USER, created.id, _HUMAN)
    assert restored.archived_at is None
    assert captured[0].action is Action.RESTORE
    assert [s.id for s in await service.list_sources(_USER)] == [created.id]


async def test_restore_of_an_active_source_is_a_conflict() -> None:
    service, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_role_write())
    with pytest.raises(Conflict):
        await service.restore(_USER, created.id, _HUMAN)


async def test_reorder_persists_sort_order_and_is_independent_per_kind() -> None:
    from floresu.profile.schemas import ReorderRequest

    service, _, _, captured = _service()
    first = await service.create(_USER, _HUMAN, build_role_write(display_label="A"))
    second = await service.create(_USER, _HUMAN, build_role_write(display_label="B"))
    third = await service.create(_USER, _HUMAN, build_role_write(display_label="C"))
    project = await service.create(_USER, _HUMAN, build_project_write())
    captured.clear()

    new_order = [third.id, first.id, second.id]
    result = await service.reorder(
        _USER, _HUMAN, ReorderRequest(kind=SourceKind.ROLE, source_ids=new_order)
    )
    assert [s.id for s in result] == new_order

    # The role section now lists in the new order; the project is untouched.
    roles = await service.list_sources(_USER, kind=SourceKind.ROLE)
    assert [s.id for s in roles] == new_order
    assert [s.sort_order for s in roles] == [0, 1, 2]
    projects = await service.list_sources(_USER, kind=SourceKind.PROJECT)
    assert [s.id for s in projects] == [project.id]
    assert projects[0].sort_order == 0

    assert len(captured) == 1
    event = captured[0]
    assert event.action is Action.REORDER
    assert event.metadata == {"kind": "role", "order": new_order}


async def test_reorder_rejects_unknown_ids() -> None:
    from floresu.profile.schemas import ReorderRequest

    service, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_role_write())
    with pytest.raises(Validation):
        await service.reorder(
            _USER, _HUMAN, ReorderRequest(kind=SourceKind.ROLE, source_ids=[created.id, 999])
        )


async def test_reorder_rejects_a_partial_section() -> None:
    from floresu.profile.schemas import ReorderRequest

    service, _, _, captured = _service()
    first = await service.create(_USER, _HUMAN, build_role_write(display_label="A"))
    await service.create(_USER, _HUMAN, build_role_write(display_label="B"))
    third = await service.create(_USER, _HUMAN, build_role_write(display_label="C"))
    captured.clear()

    # Submitting only two of the three active roles is rejected: a partial submit
    # would leave the omitted row's sort_order stale (duplicate / partial order).
    with pytest.raises(Validation):
        await service.reorder(
            _USER, _HUMAN, ReorderRequest(kind=SourceKind.ROLE, source_ids=[third.id, first.id])
        )
    # Nothing was published or reordered.
    assert captured == []


async def test_reorder_rejects_duplicate_ids() -> None:
    from floresu.profile.schemas import ReorderRequest

    service, _, _, _ = _service()
    created = await service.create(_USER, _HUMAN, build_role_write())
    with pytest.raises(Validation):
        await service.reorder(
            _USER,
            _HUMAN,
            ReorderRequest(kind=SourceKind.ROLE, source_ids=[created.id, created.id]),
        )


async def test_reorder_wrong_kind_id_is_rejected() -> None:
    from floresu.profile.schemas import ReorderRequest

    service, _, _, _ = _service()
    role = await service.create(_USER, _HUMAN, build_role_write())
    # The role id is not part of the project section.
    with pytest.raises(Validation):
        await service.reorder(
            _USER, _HUMAN, ReorderRequest(kind=SourceKind.PROJECT, source_ids=[role.id])
        )


async def test_a_malformed_identity_is_rejected() -> None:
    service, _, _, _ = _service()
    with pytest.raises(Unauthorized):
        await service.create("not-a-number", _HUMAN, build_role_write())


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def __call__(self) -> datetime:
        return self._now
