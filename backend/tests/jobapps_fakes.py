"""In-memory test doubles and factories for the job-application domain.

The lifecycle service is tested sociably: the real :class:`JobApplicationService`
runs over this in-memory repository (substituted at the only true external boundary,
Postgres), the real :class:`WriteEventPublisher` seam wired with a capturing consumer,
and a recording finalizer standing in for the resume finalize routine (which has its
own sociable tests). The repo mirrors what the database assigns on insert (server-minted
ids) and the reads the real queries do (applications newest-first) and tracks the 1:1
resume link tests seed explicitly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from floresu.resumes.models import JobApplication, JobApplicationStatus

if TYPE_CHECKING:
    from collections.abc import Sequence

    from floresu.core.actor import Actor
    from floresu.resumes.schemas import FinalizeResult

FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


class InMemoryJobApplicationRepository:
    """A dict-backed :class:`JobApplicationRepository` with real ids and the resume link."""

    def __init__(self) -> None:
        self._applications: dict[int, JobApplication] = {}
        self._links: dict[int, int] = {}  # application_id -> resume_id (the 1:1 link)
        self._next_id = 1

    def seed(self, application: JobApplication) -> JobApplication:
        """Insert an application directly (test setup), minting an id if it has none."""
        if application.id is None:
            application.id = self._next_id
            self._next_id += 1
        self._applications[application.id] = application
        return application

    def link_resume(self, application_id: int, resume_id: int) -> None:
        """Seed the 1:1 application->resume link the real query reads off ``resumes``."""
        self._links[application_id] = resume_id

    async def add(self, application: JobApplication) -> None:
        application.id = self._next_id
        self._next_id += 1
        self._applications[application.id] = application

    async def get(self, user_id: int, application_id: int) -> JobApplication | None:
        application = self._applications.get(application_id)
        if application is None or application.user_id != user_id:
            return None
        return application

    async def list_applications(self, user_id: int, *, limit: int) -> Sequence[JobApplication]:
        rows = [app for app in self._applications.values() if app.user_id == user_id]
        rows.sort(key=lambda app: app.id, reverse=True)
        return rows[:limit]

    async def linked_resume_id(self, application_id: int) -> int | None:
        return self._links.get(application_id)

    async def linked_resume_ids(self, application_ids: Sequence[int]) -> dict[int, int]:
        return {
            application_id: self._links[application_id]
            for application_id in application_ids
            if application_id in self._links
        }


class RecordingFinalizer:
    """A :class:`ResumeFinalizer` double: records finalize calls and mirrors its effect.

    Standing in for the real finalize routine in lifecycle tests, it records each call
    and marks the seeded application ``submitted`` (as the real finalize does inside its
    own transaction), so the service's re-read reflects the submitted status.
    """

    def __init__(self, repo: InMemoryJobApplicationRepository) -> None:
        self._repo = repo
        self.calls: list[tuple[str, int]] = []

    async def finalize(self, user_id: str, resume_id: int, actor: Actor) -> FinalizeResult:
        from floresu.resumes.models import ResumeStatus
        from floresu.resumes.schemas import FinalizeResult

        self.calls.append((user_id, resume_id))
        for application_id, linked in self._repo._links.items():
            if linked == resume_id:
                application = self._repo._applications.get(application_id)
                if application is not None:
                    application.status = JobApplicationStatus.SUBMITTED
        return FinalizeResult(
            resume_id=resume_id,
            status=ResumeStatus.FINALIZED,
            pdf_object_key=f"u/1/r/{resume_id}/rev/2.pdf",
            revision_no=2,
        )


def build_application(**overrides: Any) -> JobApplication:
    """A ``job_applications`` row with all response fields set (server defaults bypassed)."""
    base: dict[str, Any] = {
        "user_id": 1,
        "company": "Globex",
        "role_title": "Staff Engineer",
        "status": JobApplicationStatus.ADDED,
        "created_at": FIXED_NOW,
        "updated_at": FIXED_NOW,
    }
    base.update(overrides)
    return JobApplication(**base)
