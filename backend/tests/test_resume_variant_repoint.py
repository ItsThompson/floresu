"""Unit tests for the resume side of the identity-variant archive re-point port.

Sociable: the real :class:`ResumeService` runs over the in-memory repository, a
fake bullet-text resolver, and the real write-event seam with a capturing consumer.
:meth:`ResumeService.resumes_referencing_variant` and
:meth:`ResumeService.repoint_variant` are what the identity-variants archive drives
through the ``ResumeVariantRepointer`` port, so these assert the observable outcome:
which resumes are found, the re-pointed header, the bumped revision, the appended
snapshot, and the published ``UPDATE``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from floresu.core.actor import Actor, ActorType
from floresu.core.db import transaction
from floresu.core.events import Action
from floresu.resumes.service import ResumeService
from tests.resumes_fakes import (
    InMemoryBulletTextResolver,
    InMemoryResumeRepository,
    build_bullet_writer,
    build_create_request,
    build_update,
)
from tests.support.fakes import CapturingWriteEventPublisher, FakeSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.events import WriteEvent

_USER = "1"
_HUMAN = Actor(type=ActorType.HUMAN)


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def __call__(self) -> datetime:
        return self._now


def _service() -> tuple[
    ResumeService, InMemoryResumeRepository, FakeSession, list[WriteEvent]
]:
    repo = InMemoryResumeRepository()
    session = FakeSession()
    publisher = CapturingWriteEventPublisher()
    service = ResumeService(
        session,  # type: ignore[arg-type]
        repo,
        InMemoryBulletTextResolver(),
        publisher,
        build_bullet_writer(session, publisher),  # type: ignore[arg-type]
        clock=_FixedClock(datetime(2026, 1, 1, tzinfo=UTC)),
    )
    return service, repo, session, publisher.captured


async def _resume_referencing(service: ResumeService, variant_id: int | None) -> int:
    """Create a living resume whose header references ``variant_id``; return its id."""
    created = await service.create(_USER, _HUMAN, build_create_request())
    updated = await service.update(
        _USER,
        created.id,
        _HUMAN,
        created.revision,
        build_update(header={"identity_variant_id": variant_id}),
    )
    return updated.id


async def test_resumes_referencing_variant_finds_only_the_referencing_living_resumes() -> None:
    service, _, _, _ = _service()
    references_five = await _resume_referencing(service, 5)
    await _resume_referencing(service, 7)  # references a different variant
    await _resume_referencing(service, None)  # references none

    assert list(await service.resumes_referencing_variant(_USER, 5)) == [references_five]
    assert list(await service.resumes_referencing_variant(_USER, 999)) == []


async def test_repoint_moves_the_header_and_runs_the_save_contract() -> None:
    service, repo, session, captured = _service()
    resume_id = await _resume_referencing(service, 5)
    revision_before = (await service.get(_USER, resume_id)).revision
    captured.clear()

    async with transaction(cast("AsyncSession", session)):
        changed = await service.repoint_variant(_USER, _HUMAN, 5, 8)

    assert list(changed) == [resume_id]
    reloaded = await service.get(_USER, resume_id)
    # The header now points at the replacement, never left on the archived variant.
    assert reloaded.document.header.identity_variant_id == 8
    # The save contract ran: the revision bumped and a fresh snapshot was appended,
    # and a single UPDATE was published for the re-point.
    assert reloaded.revision == revision_before + 1
    assert repo.revision(resume_id, reloaded.revision) is not None
    assert [event.action for event in captured] == [Action.UPDATE]
    assert captured[-1].entity_type == "resume"


async def test_repoint_leaves_resumes_that_reference_other_variants_untouched() -> None:
    service, _, session, _ = _service()
    referencing = await _resume_referencing(service, 5)
    other = await _resume_referencing(service, 7)
    other_revision = (await service.get(_USER, other)).revision

    async with transaction(cast("AsyncSession", session)):
        changed = await service.repoint_variant(_USER, _HUMAN, 5, 8)

    assert list(changed) == [referencing]
    untouched = await service.get(_USER, other)
    assert untouched.document.header.identity_variant_id == 7
    assert untouched.revision == other_revision


async def test_repoint_with_no_referencing_resumes_is_a_noop() -> None:
    service, _, session, captured = _service()
    await _resume_referencing(service, 7)
    captured.clear()

    async with transaction(cast("AsyncSession", session)):
        changed = await service.repoint_variant(_USER, _HUMAN, 5, 8)

    assert list(changed) == []
    assert captured == []
