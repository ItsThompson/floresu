"""IdentityVariantService business rules, through its public methods with an
in-memory repository, the real write-event seam (capturing consumer), and the
profile fake session recording the transaction boundary (sociable). Covers the
exactly-one-default invariant, the same-transaction default flip, the archive
gates, and the replacement-required signal."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from floresu.core.actor import Actor, ActorType
from floresu.core.errors import Conflict, NotFound, Unauthorized, Validation
from floresu.core.events import Action, WriteEvent
from floresu.profile.injection import Clock
from floresu.profile.variants.config import REPLACEMENT_REQUIRED_RULE
from floresu.profile.variants.service import IdentityVariantService
from tests.variants_fakes import (
    FakeSession,
    InMemoryIdentityVariantRepository,
    build_variant_write,
    capturing_publisher,
)

_USER = "1"
_HUMAN = Actor(type=ActorType.HUMAN)
_AGENT = Actor(type=ActorType.AGENT, label="claude")


def _service(
    *, clock: Clock | None = None
) -> tuple[
    IdentityVariantService, InMemoryIdentityVariantRepository, FakeSession, list[WriteEvent]
]:
    repo = InMemoryIdentityVariantRepository()
    session = FakeSession()
    publisher, captured = capturing_publisher()
    kwargs = {"clock": clock} if clock is not None else {}
    service = IdentityVariantService(session, repo, publisher, **kwargs)  # type: ignore[arg-type]
    return service, repo, session, captured


async def test_first_variant_is_forced_default_and_captures_fields() -> None:
    service, _, session, captured = _service()
    # Created without is_default; the first variant is still made default.
    variant = await service.create(_USER, _HUMAN, build_variant_write(is_default=False))

    assert variant.id >= 1
    assert variant.label == "Personal"
    assert variant.full_name == "Ada Lovelace"
    assert variant.contact.email == "ada@example.com"
    assert variant.contact.location == "London"
    assert variant.contact.phone is None  # optional per variant
    assert [link.url for link in variant.links] == ["https://ada.example.com"]
    assert variant.is_default is True

    assert len(captured) == 1
    assert captured[0].action is Action.CREATE
    assert captured[0].entity_type == "identity_variant"
    assert captured[0].actor == _HUMAN
    assert session.commits == 1


async def test_contact_fields_are_each_optional() -> None:
    service, _, _, _ = _service()
    variant = await service.create(_USER, _HUMAN, build_variant_write(contact={}, links=[]))
    assert variant.contact.email is None
    assert variant.contact.phone is None
    assert variant.contact.location is None
    assert variant.links == []


async def test_second_variant_is_not_default_unless_requested() -> None:
    service, _, _, _ = _service()
    first = await service.create(_USER, _HUMAN, build_variant_write(label="Personal"))
    second = await service.create(_USER, _HUMAN, build_variant_write(label="Academic"))
    assert first.is_default is True
    assert second.is_default is False


async def test_creating_a_second_default_flips_the_previous_one() -> None:
    service, _, _, _ = _service()
    first = await service.create(_USER, _HUMAN, build_variant_write(label="Personal"))
    second = await service.create(
        _USER, _HUMAN, build_variant_write(label="Academic", is_default=True)
    )
    assert second.is_default is True
    # The previous default flipped off in the same write.
    refetched_first = await service.get(_USER, first.id)
    assert refetched_first.is_default is False


async def test_marking_a_different_variant_default_flips_the_old_one() -> None:
    service, _, _, captured = _service()
    first = await service.create(_USER, _HUMAN, build_variant_write(label="Personal"))
    second = await service.create(_USER, _HUMAN, build_variant_write(label="Academic"))
    captured.clear()

    promoted = await service.update(
        _USER, second.id, _HUMAN, build_variant_write(label="Academic", is_default=True)
    )
    assert promoted.is_default is True
    assert (await service.get(_USER, first.id)).is_default is False

    # Exactly one default exists.
    actives = await service.list_variants(_USER)
    assert [v.is_default for v in actives].count(True) == 1
    # The promotion recorded an update carrying the default marker.
    assert captured[0].action is Action.UPDATE
    assert captured[0].metadata == {"is_default": True}


async def test_editing_a_non_default_variant_without_promoting_keeps_it_non_default() -> None:
    service, _, _, _ = _service()
    await service.create(_USER, _HUMAN, build_variant_write(label="Personal"))
    second = await service.create(_USER, _HUMAN, build_variant_write(label="Academic"))

    # Edit the non-default variant's name with is_default=False: it stays non-default.
    edited = await service.update(
        _USER,
        second.id,
        _HUMAN,
        build_variant_write(label="Academic", full_name="Grace Hopper", is_default=False),
    )
    assert edited.full_name == "Grace Hopper"
    assert edited.is_default is False


async def test_the_default_cannot_be_unset_directly() -> None:
    service, _, _, _ = _service()
    first = await service.create(_USER, _HUMAN, build_variant_write(label="Personal"))
    # Trying to set the sole default's is_default to False is rejected.
    with pytest.raises(Conflict):
        await service.update(
            _USER, first.id, _HUMAN, build_variant_write(label="Personal", is_default=False)
        )


async def test_updating_a_non_default_field_keeps_the_default_stable() -> None:
    service, _, _, _ = _service()
    first = await service.create(_USER, _HUMAN, build_variant_write(label="Personal"))
    second = await service.create(_USER, _HUMAN, build_variant_write(label="Academic"))

    # Editing the default's name without touching is_default keeps it default.
    edited = await service.update(
        _USER,
        first.id,
        _HUMAN,
        build_variant_write(label="Personal", full_name="Ada L.", is_default=True),
    )
    assert edited.is_default is True
    assert edited.full_name == "Ada L."
    assert (await service.get(_USER, second.id)).is_default is False


async def test_default_variant_cannot_be_archived_until_another_is_default() -> None:
    service, _, _, _ = _service()
    first = await service.create(_USER, _HUMAN, build_variant_write(label="Personal"))
    second = await service.create(_USER, _HUMAN, build_variant_write(label="Academic"))

    # first is default; archiving it is blocked.
    with pytest.raises(Conflict):
        await service.archive(_USER, first.id, _HUMAN)

    # Promote second, then first can be archived.
    await service.update(
        _USER, second.id, _HUMAN, build_variant_write(label="Academic", is_default=True)
    )
    archived = await service.archive(_USER, first.id, _HUMAN)
    assert archived.archived_at is not None


async def test_non_default_variant_archives_normally() -> None:
    clock = _FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    service, _, _, captured = _service(clock=clock)
    await service.create(_USER, _HUMAN, build_variant_write(label="Personal"))
    second = await service.create(_USER, _HUMAN, build_variant_write(label="Academic"))
    captured.clear()

    archived = await service.archive(_USER, second.id, _HUMAN)
    assert archived.archived_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert captured[0].action is Action.ARCHIVE
    assert await service.list_variants(_USER) != []  # the default remains active


async def test_archiving_a_referenced_variant_surfaces_a_replacement_signal() -> None:
    service, repo, _, captured = _service()
    await service.create(_USER, _HUMAN, build_variant_write(label="Personal"))
    second = await service.create(_USER, _HUMAN, build_variant_write(label="Academic"))
    # Seed a living resume referencing the (non-default) second variant.
    repo.set_references(1, second.id, [42, 43])
    captured.clear()

    with pytest.raises(Validation) as excinfo:
        await service.archive(_USER, second.id, _HUMAN)

    # The signal names the rule and the referencing resume ids, and nothing archived.
    violations = excinfo.value.violations
    assert len(violations) == 1
    assert violations[0].rule == REPLACEMENT_REQUIRED_RULE
    assert violations[0].ids == ["42", "43"]
    assert captured == []
    assert (await service.get(_USER, second.id)).archived_at is None


async def test_a_duplicate_label_is_a_conflict() -> None:
    service, _, _, _ = _service()
    await service.create(_USER, _HUMAN, build_variant_write(label="Personal"))
    with pytest.raises(Conflict):
        await service.create(_USER, _HUMAN, build_variant_write(label="Personal"))


async def test_restore_returns_a_variant_and_it_is_not_default() -> None:
    service, _, _, _ = _service()
    await service.create(_USER, _HUMAN, build_variant_write(label="Personal"))
    second = await service.create(_USER, _HUMAN, build_variant_write(label="Academic"))
    await service.archive(_USER, second.id, _HUMAN)

    restored = await service.restore(_USER, second.id, _HUMAN)
    assert restored.archived_at is None
    assert restored.is_default is False


async def test_double_archive_is_a_conflict() -> None:
    service, _, _, _ = _service()
    await service.create(_USER, _HUMAN, build_variant_write(label="Personal"))
    second = await service.create(_USER, _HUMAN, build_variant_write(label="Academic"))
    await service.archive(_USER, second.id, _HUMAN)
    with pytest.raises(Conflict):
        await service.archive(_USER, second.id, _HUMAN)


async def test_restore_of_an_active_variant_is_a_conflict() -> None:
    service, _, _, _ = _service()
    first = await service.create(_USER, _HUMAN, build_variant_write(label="Personal"))
    with pytest.raises(Conflict):
        await service.restore(_USER, first.id, _HUMAN)


async def test_agent_writes_carry_the_named_agent_actor() -> None:
    service, _, _, captured = _service()
    await service.create(_USER, _AGENT, build_variant_write())
    assert captured[0].actor == _AGENT
    assert captured[0].actor.label == "claude"


async def test_mutations_of_a_missing_variant_are_not_found() -> None:
    service, _, _, _ = _service()
    with pytest.raises(NotFound):
        await service.get(_USER, 999)
    with pytest.raises(NotFound):
        await service.update(_USER, 999, _HUMAN, build_variant_write())
    with pytest.raises(NotFound):
        await service.archive(_USER, 999, _HUMAN)
    with pytest.raises(NotFound):
        await service.restore(_USER, 999, _HUMAN)


async def test_another_users_variant_is_not_found_no_existence_leak() -> None:
    service, _, _, _ = _service()
    mine = await service.create(_USER, _HUMAN, build_variant_write())
    with pytest.raises(NotFound):
        await service.get("2", mine.id)


async def test_a_malformed_identity_is_rejected() -> None:
    service, _, _, _ = _service()
    with pytest.raises(Unauthorized):
        await service.create("not-a-number", _HUMAN, build_variant_write())


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def __call__(self) -> datetime:
        return self._now
