"""Sociable tests for the job-application lifecycle service.

The real :class:`JobApplicationService` runs over the in-memory repository, the real
write-event seam with a capturing consumer, and a recording finalizer (the resume
finalize routine has its own tests). Covers create-at-added, the list/get read shapes
with the linked resume, plain field edits, and the submit=finalize trigger in every
branch: it finalizes a linked resume, is rejected (recoverably) with no linked resume,
is an idempotent no-op when already submitted, and refuses to revert to added.
"""

from __future__ import annotations

import pytest

from floresu.core.actor import Actor, ActorType
from floresu.core.errors import Conflict, NotFound
from floresu.core.events import Action, WriteEvent, WriteEventPublisher
from floresu.jobapps.schemas import JobApplicationCreate, JobApplicationUpdate
from floresu.jobapps.service import JobApplicationService
from floresu.resumes.models import JobApplicationStatus
from tests.jobapps_fakes import (
    FIXED_NOW,
    InMemoryJobApplicationRepository,
    RecordingFinalizer,
    build_application,
)
from tests.resumes_fakes import FakeSession, capturing_publisher

_HUMAN = Actor(type=ActorType.HUMAN)
_USER = "1"


def _service(
    repo: InMemoryJobApplicationRepository,
    publisher: WriteEventPublisher,
    finalizer: RecordingFinalizer,
) -> JobApplicationService:
    return JobApplicationService(
        FakeSession(),  # type: ignore[arg-type]
        repo,
        publisher,
        finalizer,
        clock=lambda: FIXED_NOW,
    )


def _setup() -> tuple[
    JobApplicationService, InMemoryJobApplicationRepository, list[WriteEvent], RecordingFinalizer
]:
    repo = InMemoryJobApplicationRepository()
    publisher, captured = capturing_publisher()
    finalizer = RecordingFinalizer(repo)
    return _service(repo, publisher, finalizer), repo, captured, finalizer


@pytest.mark.asyncio
async def test_create_starts_added_and_audits() -> None:
    service, _repo, captured, _finalizer = _setup()

    summary = await service.create(
        _USER, _HUMAN, JobApplicationCreate(company="Initech", role_title="Backend Engineer")
    )

    assert summary.status is JobApplicationStatus.ADDED
    assert summary.company == "Initech"
    assert summary.linked_resume_id is None
    assert [event.action for event in captured] == [Action.CREATE]
    assert captured[0].entity_type == "job_application"


@pytest.mark.asyncio
async def test_list_returns_newest_first_with_linked_resume() -> None:
    service, repo, _captured, _finalizer = _setup()
    first = repo.seed(build_application(company="Aperture"))
    second = repo.seed(build_application(company="Globex"))
    repo.link_resume(first.id, resume_id=42)

    summaries = await service.list_applications(_USER)

    assert [summary.id for summary in summaries] == [second.id, first.id]
    linked = {summary.id: summary.linked_resume_id for summary in summaries}
    assert linked == {first.id: 42, second.id: None}


@pytest.mark.asyncio
async def test_get_returns_linked_resume_id() -> None:
    service, repo, _captured, _finalizer = _setup()
    application = repo.seed(build_application())
    repo.link_resume(application.id, resume_id=7)

    summary = await service.get(_USER, application.id)

    assert summary.linked_resume_id == 7


@pytest.mark.asyncio
async def test_get_unknown_is_not_found() -> None:
    service, _repo, _captured, _finalizer = _setup()

    with pytest.raises(NotFound):
        await service.get(_USER, 999)


@pytest.mark.asyncio
async def test_update_company_edits_and_audits_without_finalizing() -> None:
    service, repo, captured, finalizer = _setup()
    application = repo.seed(build_application(company="Old", role_title="SWE"))

    summary = await service.update(
        _USER, _HUMAN, application.id, JobApplicationUpdate(company="New")
    )

    assert summary.company == "New"
    assert summary.status is JobApplicationStatus.ADDED
    assert finalizer.calls == []
    assert [event.action for event in captured] == [Action.UPDATE]


@pytest.mark.asyncio
async def test_submit_finalizes_the_linked_resume() -> None:
    service, repo, _captured, finalizer = _setup()
    application = repo.seed(build_application())
    repo.link_resume(application.id, resume_id=55)

    summary = await service.update(
        _USER, _HUMAN, application.id, JobApplicationUpdate(status=JobApplicationStatus.SUBMITTED)
    )

    assert finalizer.calls == [(_USER, 55)]
    assert summary.status is JobApplicationStatus.SUBMITTED


@pytest.mark.asyncio
async def test_submit_without_linked_resume_is_rejected_and_stays_added() -> None:
    service, repo, captured, finalizer = _setup()
    application = repo.seed(build_application())

    with pytest.raises(Conflict):
        await service.update(
            _USER,
            _HUMAN,
            application.id,
            JobApplicationUpdate(status=JobApplicationStatus.SUBMITTED),
        )

    assert finalizer.calls == []
    assert application.status is JobApplicationStatus.ADDED
    assert captured == []


@pytest.mark.asyncio
async def test_submit_when_already_submitted_is_idempotent_noop() -> None:
    service, repo, captured, finalizer = _setup()
    application = repo.seed(build_application(status=JobApplicationStatus.SUBMITTED))
    repo.link_resume(application.id, resume_id=8)

    summary = await service.update(
        _USER, _HUMAN, application.id, JobApplicationUpdate(status=JobApplicationStatus.SUBMITTED)
    )

    assert finalizer.calls == []
    assert captured == []
    assert summary.status is JobApplicationStatus.SUBMITTED


@pytest.mark.asyncio
async def test_revert_submitted_to_added_is_rejected() -> None:
    service, repo, _captured, _finalizer = _setup()
    application = repo.seed(build_application(status=JobApplicationStatus.SUBMITTED))

    with pytest.raises(Conflict):
        await service.update(
            _USER, _HUMAN, application.id, JobApplicationUpdate(status=JobApplicationStatus.ADDED)
        )


def test_empty_update_is_rejected_at_the_schema() -> None:
    with pytest.raises(ValueError, match="company, role_title"):
        JobApplicationUpdate()
