"""ResumeRenderService: resolve a resume, render its PDF, stream or persist it.

The rendering orchestration for the Output layer. It resolves a resume into a fully
resolved document (references inlined to text, the identity variant snapshotted into
the header), asks the pure render module for PDF bytes, and either returns them for
streaming (preview, never stored) or persists them to object storage and records the
object key (export). The render module stays pure; this service owns the
resume-specific resolution, the object-store write, and the write-event publish.

The two paths resolve different documents on purpose:

- **Preview** renders the *live* document, resolving references to the current
  library text, so an editor sees current content while editing.
- **Export** renders the *latest revision's* frozen document (its references were
  resolved to text when the revision was saved), so the persisted PDF matches that
  revision and a later library edit never changes it. It is stored under the
  revision-keyed object key and the key is recorded on that revision.

A render failure (a malformed document or a Typst error) raises
:class:`~floresu.rendering.errors.RenderError` (422), so the preview surfaces an
error state and an export is blocked with a recoverable message rather than
presenting or persisting a stale or partial artifact.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.core.db import transaction
from floresu.core.events import Action, WriteEvent
from floresu.core.observability import track_failures
from floresu.rendering.config import PDF_MEDIA_TYPE
from floresu.rendering.errors import RenderError
from floresu.resumes.config import ENTITY_TYPE
from floresu.resumes.document import (
    ResumeDocument,
    ResumeHeader,
    referenced_bullet_ids,
    resolve_document,
)
from floresu.resumes.operations import require_user_pk, resume_not_found
from floresu.resumes.render_schemas import ExportResult
from floresu.resumes.upcast import load_document
from floresu.storage.keys import revision_pdf_key

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from floresu.core.actor import Actor
    from floresu.core.events import WriteEventPublisher
    from floresu.rendering.module import RenderModule
    from floresu.rendering.schemas import TemplateInfo
    from floresu.resumes.identity_resolver import IdentityResolver
    from floresu.resumes.models import Resume
    from floresu.resumes.render_repository import RenderRepository
    from floresu.resumes.resolver import BulletTextResolver
    from floresu.storage.store import ObjectStore

_EXPORT_SUMMARY = "Exported resume PDF"


@track_failures("resume_rendering")
class ResumeRenderService:
    """Resolve, render, and (for export) persist a resume PDF; the render module stays pure."""

    def __init__(
        self,
        session: AsyncSession,
        repo: RenderRepository,
        bullet_resolver: BulletTextResolver,
        identity_resolver: IdentityResolver,
        render_module: RenderModule,
        object_store: ObjectStore,
        publisher: WriteEventPublisher,
    ) -> None:
        self._session = session
        self._repo = repo
        self._bullets = bullet_resolver
        self._identity = identity_resolver
        self._render = render_module
        self._store = object_store
        self._publisher = publisher

    def list_templates(self) -> list[TemplateInfo]:
        """The global template registry entries the selector lists."""
        return self._render.list_templates()

    async def preview(self, user_id: str, resume_id: int, template_id: str | None = None) -> bytes:
        """Render the live document to ephemeral PDF bytes (never stored)."""
        pk = require_user_pk(user_id)
        resume = await self._load(pk, resume_id)
        document = load_document(resume.document)
        resolved = await self._resolve_live(pk, document)
        return await self._render.render(resolved, template_id or document.template_id)

    async def export(self, user_id: str, resume_id: int, actor: Actor) -> ExportResult:
        """Render the latest revision, persist it to R2, and record its object key."""
        pk = require_user_pk(user_id)
        await self._load(pk, resume_id)
        revision = await self._repo.latest_revision(resume_id)
        if revision is None:
            raise RenderError("This resume has no saved revision to export.")
        document = load_document(revision.document)
        resolved = await self._resolve_frozen(pk, document)
        pdf = await self._render.render(resolved, document.template_id)
        key = revision_pdf_key(pk, resume_id, revision.revision_no)
        await self._store.put(key, pdf, PDF_MEDIA_TYPE)
        async with transaction(self._session):
            await self._repo.set_revision_pdf_key(resume_id, revision.revision_no, key)
            await self._publish(pk, actor, resume_id, revision.revision_no, document.template_id)
        url = await self._store.get_url(key)
        return ExportResult(
            resume_id=resume_id, revision=revision.revision_no, object_key=key, download_url=url
        )

    async def _load(self, pk: int, resume_id: int) -> Resume:
        resume = await self._repo.get_resume(pk, resume_id)
        if resume is None:
            raise resume_not_found(resume_id)
        return resume

    async def _resolve_live(self, pk: int, document: ResumeDocument) -> ResumeDocument:
        """Resolve references to the current library text, then snapshot the identity."""
        ref_ids = referenced_bullet_ids(document)
        texts = await self._bullets.resolve(pk, ref_ids) if ref_ids else {}
        missing = [bullet_id for bullet_id in ref_ids if bullet_id not in texts]
        if missing:
            raise RenderError(
                f"This resume references a bulletpoint that no longer exists: {missing}."
            )
        resolved = resolve_document(document, texts)
        return await self._with_identity(pk, document, resolved)

    async def _resolve_frozen(self, pk: int, document: ResumeDocument) -> ResumeDocument:
        """A revision document is already reference-resolved; only the identity resolves."""
        return await self._with_identity(pk, document, document)

    async def _with_identity(
        self, pk: int, source: ResumeDocument, resolved: ResumeDocument
    ) -> ResumeDocument:
        """Return ``resolved`` with its header carrying the resolved identity snapshot."""
        snapshot = source.header.identity_snapshot
        if snapshot is None:
            snapshot = await self._identity.resolve(pk, source.header.identity_variant_id)
        return resolved.model_copy(update={"header": ResumeHeader(identity_snapshot=snapshot)})

    async def _publish(
        self, pk: int, actor: Actor, resume_id: int, revision_no: int, template_id: str
    ) -> None:
        await self._publisher.publish(
            self._session,
            WriteEvent(
                user_id=pk,
                actor=actor,
                entity_type=ENTITY_TYPE,
                entity_id=resume_id,
                action=Action.RENDER,
                summary=_EXPORT_SUMMARY,
                metadata={"template": template_id, "revision": revision_no},
            ),
        )
