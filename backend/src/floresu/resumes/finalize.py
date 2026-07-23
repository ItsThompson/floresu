"""ResumeFinalizeService: freeze an application resume and sync its job application.

Finalize makes "what I sent" permanent and detaches the resume from the library so
a later library edit can never change it. Two triggers converge here: marking a
linked job application ``submitted`` (the lifecycle service calls this) and
finalizing the resume directly. The routine is guarded to application drafts and,
in one transaction, freezes and stores the frozen artifact:

1. resolve every ``library_ref`` item to inline text (resolved once via T12's
   :func:`resolve_document`, ``forked_from_bullet_id`` retained), so the document
   holds zero references;
2. snapshot the header identity variant inline (frozen contact facts);
3. flip the status to ``finalized`` and drop all ``resume_bullet_ref`` rows, so the
   resume never again contributes to any bullet's "used in N";
4. render the frozen document to a PDF, store it in R2, and record the object key on
   the appended frozen revision snapshot;
5. if a job application is linked, set it ``submitted`` (idempotent);
6. publish a ``finalize`` write event (and, on a real transition, a job-application
   ``update``) through the one audit/feed seam.

The R2 put runs before the transaction (mirroring export), so a recorded key never
points at a missing object; the revision-keyed name makes a re-render self-healing.
A finalized resume is read-only afterward (the existing editable guard rejects every
mutation); the only way to change it is to fork a new draft copy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from floresu.core.conflicts import conflict_on_duplicate
from floresu.core.db import transaction
from floresu.core.errors import Validation
from floresu.core.events import Action, emit_write_event
from floresu.core.observability import track_failures
from floresu.jobapps.config import ENTITY_TYPE as JOB_APPLICATION_ENTITY_TYPE
from floresu.rendering.config import PDF_MEDIA_TYPE
from floresu.resumes.config import CONCURRENT_WRITE_CONFLICT, ENTITY_TYPE
from floresu.resumes.document import (
    ResumeDocument,
    ResumeHeader,
    referenced_bullet_ids,
    resolve_document,
)
from floresu.resumes.injection import Clock, utcnow
from floresu.resumes.models import (
    JobApplicationStatus,
    Resume,
    ResumeRevision,
    ResumeStatus,
)
from floresu.resumes.operations import guard_finalizable, require_user_pk, resume_not_found
from floresu.resumes.schemas import FinalizeResult
from floresu.resumes.upcast import CURRENT_SCHEMA_VERSION, load_document
from floresu.storage.keys import revision_pdf_key

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.actor import Actor
    from floresu.core.events import WriteEventPublisher
    from floresu.jobapps.repository import JobApplicationRepository
    from floresu.rendering.module import RenderModule
    from floresu.resumes.identity_resolver import IdentityResolver
    from floresu.resumes.repository import ResumeRepository
    from floresu.resumes.resolver import BulletTextResolver
    from floresu.storage.store import ObjectStore


class ResumeFinalizer(Protocol):
    """The narrow port the job-application lifecycle depends on to finalize its resume."""

    async def finalize(self, user_id: str, resume_id: int, actor: Actor) -> FinalizeResult: ...


@track_failures("resume_finalize")
class ResumeFinalizeService:
    """Freeze an application resume to inline read-only content and sync its application."""

    def __init__(
        self,
        session: AsyncSession,
        repo: ResumeRepository,
        bullet_resolver: BulletTextResolver,
        identity_resolver: IdentityResolver,
        render_module: RenderModule,
        object_store: ObjectStore,
        job_applications: JobApplicationRepository,
        publisher: WriteEventPublisher,
        *,
        clock: Clock = utcnow,
    ) -> None:
        self._session = session
        self._repo = repo
        self._bullets = bullet_resolver
        self._identity = identity_resolver
        self._render = render_module
        self._store = object_store
        self._job_applications = job_applications
        self._publisher = publisher
        self._clock = clock

    async def finalize(self, user_id: str, resume_id: int, actor: Actor) -> FinalizeResult:
        """Freeze the application draft, store its PDF, and submit a linked application."""
        pk = require_user_pk(user_id)
        resume = await self._load(pk, resume_id)
        guard_finalizable(resume)
        frozen = await self._freeze_document(pk, load_document(resume.document))
        revision_no = resume.revision + 1
        pdf = await self._render.render(frozen, frozen.template_id)
        key = revision_pdf_key(pk, resume_id, revision_no)
        # Put to R2 before the record transaction, so a recorded key never points at
        # a missing object; the revision-keyed name makes a re-render overwrite it.
        await self._store.put(key, pdf, PDF_MEDIA_TYPE)
        async with transaction(self._session):
            self._apply_finalized(resume, frozen, revision_no)
            await self._repo.set_bullet_refs(resume_id, [])
            # Finalize takes no If-Match (it is terminal, not among the guarded
            # resume mutations), so a concurrent draft edit or a double-submit that
            # committed revision_no first would collide on the (resume_id,
            # revision_no) PK. Remap that race to a recoverable conflict, mirroring
            # ResumeService, rather than surfacing a 500.
            async with conflict_on_duplicate(CONCURRENT_WRITE_CONFLICT):
                await self._repo.add_revision(
                    ResumeRevision(
                        resume_id=resume_id,
                        revision_no=revision_no,
                        document=frozen.model_dump(mode="json"),
                        schema_version=CURRENT_SCHEMA_VERSION,
                        pdf_object_key=key,
                    )
                )
            await self._sync_job_application(pk, resume, actor)
            await self._publish_finalize(pk, actor, resume_id, revision_no, key, frozen.template_id)
        return FinalizeResult(
            resume_id=resume_id,
            status=ResumeStatus.FINALIZED,
            pdf_object_key=key,
            revision_no=revision_no,
        )

    async def _freeze_document(self, pk: int, document: ResumeDocument) -> ResumeDocument:
        """Inline every reference to text and snapshot the identity into the header."""
        ref_ids = referenced_bullet_ids(document)
        texts = await self._bullets.resolve(pk, ref_ids) if ref_ids else {}
        missing = [bullet_id for bullet_id in ref_ids if bullet_id not in texts]
        if missing:
            raise Validation(
                "This resume references a bulletpoint that does not exist or is not yours, "
                "so it cannot be finalized.",
                fields={"items": f"Unknown bullet id(s): {missing}."},
            )
        resolved = resolve_document(document, texts)
        snapshot = document.header.identity_snapshot
        if snapshot is None:
            snapshot = await self._identity.resolve(pk, document.header.identity_variant_id)
        return resolved.model_copy(update={"header": ResumeHeader(identity_snapshot=snapshot)})

    def _apply_finalized(self, resume: Resume, frozen: ResumeDocument, revision_no: int) -> None:
        """Persist the frozen document row: inline content, finalized status, bumped revision."""
        resume.document = frozen.model_dump(mode="json")
        resume.status = ResumeStatus.FINALIZED
        resume.schema_version = CURRENT_SCHEMA_VERSION
        resume.revision = revision_no
        resume.updated_at = self._clock()

    async def _sync_job_application(self, pk: int, resume: Resume, actor: Actor) -> None:
        """Set a linked application ``submitted`` (idempotent); standalone drafts no-op."""
        if resume.job_application_id is None:
            return
        application = await self._job_applications.get(pk, resume.job_application_id)
        if application is None or application.status is JobApplicationStatus.SUBMITTED:
            return
        application.status = JobApplicationStatus.SUBMITTED
        application.updated_at = self._clock()
        await self._publish(
            pk,
            actor,
            JOB_APPLICATION_ENTITY_TYPE,
            application.id,
            Action.UPDATE,
            summary="Marked application submitted (resume finalized)",
            metadata={"status": JobApplicationStatus.SUBMITTED.value},
        )

    async def _publish_finalize(
        self,
        pk: int,
        actor: Actor,
        resume_id: int,
        revision_no: int,
        pdf_object_key: str,
        template_id: str,
    ) -> None:
        await self._publish(
            pk,
            actor,
            ENTITY_TYPE,
            resume_id,
            Action.FINALIZE,
            summary="Finalized resume",
            metadata={
                "revision": revision_no,
                "pdf_object_key": pdf_object_key,
                "template": template_id,
            },
        )

    async def _load(self, pk: int, resume_id: int) -> Resume:
        resume = await self._repo.get(pk, resume_id)
        if resume is None:
            raise resume_not_found(resume_id)
        return resume

    async def _publish(
        self,
        user_pk: int,
        actor: Actor,
        entity_type: str,
        entity_id: int,
        action: Action,
        *,
        summary: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        await emit_write_event(
            self._publisher,
            self._session,
            user_id=user_pk,
            actor=actor,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            summary=summary,
            metadata=metadata,
        )
