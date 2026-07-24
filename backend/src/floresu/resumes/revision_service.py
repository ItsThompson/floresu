"""ResumeRevisionService: list a resume's published versions and serve one's PDF.

A published version is a revision whose PDF was rendered and stored in R2 by an
export or a finalize (``pdf_object_key`` is set); a plain per-save snapshot has no
PDF and is never listed. This service never renders: it reads the stored objects and
mints a time-limited presigned URL for one. Both operations are reads, so the service
owns no transaction and publishes no write event.

Ownership is enforced by loading the resume through the user-scoped ``get_resume``
first: a resume another account owns is scoped out of the read, so a miss is a 404
with no existence leak, exactly as the render service does it. A revision that does
not exist, or exists but has no stored PDF, is a recoverable 404 rather than a 500 or
a wrong object.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from floresu.core.errors import NotFound
from floresu.core.identity import resolve_user_pk
from floresu.core.logging import get_logger
from floresu.core.observability import track_failures
from floresu.resumes.operations import resume_not_found
from floresu.resumes.revision_schemas import (
    PublishedVersion,
    PublishedVersionList,
    VersionPdfUrl,
)

if TYPE_CHECKING:
    from floresu.resumes.models import Resume
    from floresu.resumes.render_repository import RenderRepository
    from floresu.storage.store import ObjectStore

_log = get_logger("floresu-resume-revisions")


@track_failures("resume_revisions")
class ResumeRevisionService:
    """List a resume's published versions and mint a URL for one version's stored PDF."""

    def __init__(self, repo: RenderRepository, object_store: ObjectStore) -> None:
        self._repo = repo
        self._store = object_store

    async def list_published_versions(self, user_id: str, resume_id: int) -> PublishedVersionList:
        """Newest-first list of revisions with a stored PDF; a missing resume is a 404."""
        pk = resolve_user_pk(user_id)
        await self._load(pk, resume_id)
        revisions = await self._repo.list_revisions_with_pdf(resume_id)
        versions = [PublishedVersion.model_validate(revision) for revision in revisions]
        return PublishedVersionList(resume_id=resume_id, versions=versions)

    async def version_pdf_url(
        self, user_id: str, resume_id: int, revision_no: int
    ) -> VersionPdfUrl:
        """Presigned URL for one version's PDF; a missing resume/version/object is a 404."""
        pk = resolve_user_pk(user_id)
        await self._load(pk, resume_id)
        revision = await self._repo.get_revision(resume_id, revision_no)
        if revision is None or revision.pdf_object_key is None:
            raise NotFound("That version has no stored PDF.")
        url = await self._store.get_url(revision.pdf_object_key)
        return VersionPdfUrl(resume_id=resume_id, revision_no=revision_no, download_url=url)

    async def _load(self, pk: int, resume_id: int) -> Resume:
        resume = await self._repo.get_resume(pk, resume_id)
        if resume is None:
            raise resume_not_found(resume_id)
        return resume
