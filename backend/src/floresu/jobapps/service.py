"""JobApplicationService: the job-application lifecycle and the submit=finalize trigger.

The single home for job-application rules and transactions, so the web and agent
adapters stay thin. Create starts an application at ``added`` (company + role title);
update changes the company/role title or sets the status. Setting the status to
``submitted`` is the P0 finalize trigger: it finalizes the linked 1:1 application
resume through the injected :class:`ResumeFinalizer`, which freezes the resume and
(inside its own transaction) marks this application ``submitted``, so the resume and
its application are kept consistent in one logical flow. Submitting an application
that has no linked resume is rejected with a recoverable conflict and the status
stays ``added`` (there is nothing to freeze). Every write publishes exactly one
:class:`WriteEvent` through the shared audit/feed seam.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from floresu.core.db import transaction
from floresu.core.errors import Conflict, NotFound
from floresu.core.events import Action, emit_write_event
from floresu.core.identity import resolve_user_pk
from floresu.core.observability import track_failures
from floresu.jobapps.config import DEFAULT_LIST_LIMIT, ENTITY_TYPE
from floresu.jobapps.schemas import (
    JobApplicationCreate,
    JobApplicationSummary,
    JobApplicationUpdate,
    to_summary,
)
from floresu.resumes.injection import Clock, utcnow
from floresu.resumes.models import JobApplication, JobApplicationStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.actor import Actor
    from floresu.core.events import WriteEventPublisher
    from floresu.jobapps.repository import JobApplicationRepository
    from floresu.resumes.finalize import ResumeFinalizer


@track_failures("job_applications")
class JobApplicationService:
    """Business rules for the job-application lifecycle and the submit=finalize convergence."""

    def __init__(
        self,
        session: AsyncSession,
        repo: JobApplicationRepository,
        publisher: WriteEventPublisher,
        finalizer: ResumeFinalizer,
        *,
        clock: Clock = utcnow,
    ) -> None:
        self._session = session
        self._repo = repo
        self._publisher = publisher
        self._finalizer = finalizer
        self._clock = clock

    async def create(
        self, user_id: str, actor: Actor, request: JobApplicationCreate
    ) -> JobApplicationSummary:
        """Create an application at ``added`` (company + role title); audit the write."""
        pk = resolve_user_pk(user_id)
        now = self._clock()
        application = JobApplication(
            user_id=pk,
            company=request.company,
            role_title=request.role_title,
            status=JobApplicationStatus.ADDED,
            created_at=now,
            updated_at=now,
        )
        async with transaction(self._session):
            await self._repo.add(application)
            await self._publish(
                pk,
                actor,
                application.id,
                Action.CREATE,
                summary=f"Added application: {application.role_title} at {application.company}",
            )
        return to_summary(application, linked_resume_id=None)

    async def list_applications(self, user_id: str) -> list[JobApplicationSummary]:
        """List a user's applications newest-first, each with its linked resume id."""
        pk = resolve_user_pk(user_id)
        applications = await self._repo.list_applications(pk, limit=DEFAULT_LIST_LIMIT)
        links = await self._repo.linked_resume_ids([app.id for app in applications])
        return [to_summary(app, linked_resume_id=links.get(app.id)) for app in applications]

    async def get(self, user_id: str, application_id: int) -> JobApplicationSummary:
        """Read one application with its linked resume id (404 if not the user's)."""
        pk = resolve_user_pk(user_id)
        application = await self._load(pk, application_id)
        linked = await self._repo.linked_resume_id(application_id)
        return to_summary(application, linked_resume_id=linked)

    async def update(
        self, user_id: str, actor: Actor, application_id: int, request: JobApplicationUpdate
    ) -> JobApplicationSummary:
        """Edit the company/role title and/or set the status; ``submitted`` finalizes.

        Field edits commit in one audited write. Setting ``submitted`` finalizes the
        linked resume (which marks this application submitted); an application with no
        linked resume is rejected up front and its status stays ``added``. Reverting a
        submitted application to ``added`` is rejected (finalize is terminal).
        """
        pk = resolve_user_pk(user_id)
        application = await self._load(pk, application_id)
        submitting = (
            request.status is JobApplicationStatus.SUBMITTED
            and application.status is not JobApplicationStatus.SUBMITTED
        )
        if (
            request.status is JobApplicationStatus.ADDED
            and application.status is JobApplicationStatus.SUBMITTED
        ):
            raise Conflict("A submitted application cannot return to added.")
        resume_id: int | None = None
        if submitting:
            resume_id = await self._repo.linked_resume_id(application_id)
            if resume_id is None:
                raise Conflict(
                    "This application has no linked resume to finalize; link an application "
                    "resume before submitting. The status stays added."
                )
        if self._apply_fields(application, request):
            summary = f"Updated application at {application.company}"
            async with transaction(self._session):
                application.updated_at = self._clock()
                await self._publish(pk, actor, application.id, Action.UPDATE, summary=summary)
        if submitting:
            assert resume_id is not None  # guaranteed by the submitting guard above
            await self._finalizer.finalize(user_id, resume_id, actor)
            application = await self._load(pk, application_id)
        linked = await self._repo.linked_resume_id(application_id)
        return to_summary(application, linked_resume_id=linked)

    @staticmethod
    def _apply_fields(application: JobApplication, request: JobApplicationUpdate) -> bool:
        """Apply the company/role-title edits in place; return whether anything changed."""
        changed = False
        if request.company is not None and request.company != application.company:
            application.company = request.company
            changed = True
        if request.role_title is not None and request.role_title != application.role_title:
            application.role_title = request.role_title
            changed = True
        return changed

    async def _load(self, pk: int, application_id: int) -> JobApplication:
        application = await self._repo.get(pk, application_id)
        if application is None:
            # 404-over-403: an application another account owns is scoped out of the
            # read, so a miss is indistinguishable from "does not exist".
            raise NotFound(f"No job application with id {application_id}.")
        return application

    async def _publish(
        self,
        user_pk: int,
        actor: Actor,
        entity_id: int,
        action: Action,
        *,
        summary: str,
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
