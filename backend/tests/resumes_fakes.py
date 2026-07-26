"""In-memory test doubles and factories for the resume domain.

The service is tested sociably: the real :class:`ResumeService` runs over this
in-memory repository (substituted at the only true external boundary, Postgres), a
fake bullet-text resolver, the real :class:`WriteEventPublisher` seam wired with a
capturing consumer, and a fake session that records the ``transaction`` boundary's
commit/rollback. The repo mirrors what the database assigns on insert (server-minted
ids) and the reads the real queries do (resumes newest-first). Job-application
ownership and canonical bullet text are seeded explicitly, since a resume links and
references items other domains own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from floresu.core.events import WriteEventPublisher
from floresu.library.cow import LibraryCanonicalBulletWriter
from floresu.resumes.models import Resume, ResumeKind, ResumeRevision
from floresu.resumes.schemas import (
    AddItemRequest,
    ResumeCreateRequest,
    ResumeUpdate,
)
from tests.library_fakes import InMemoryLibraryRepository
from tests.support.fakes import owned_from

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession


class InMemoryResumeRepository:
    """A dict-backed :class:`ResumeRepository` with real ids and ownership scoping."""

    def __init__(self) -> None:
        self._resumes: dict[int, Resume] = {}
        self._next_id = 1
        self._bullet_refs: dict[int, list[int]] = {}
        self._revisions: dict[tuple[int, int], ResumeRevision] = {}
        self._owned_job_applications: dict[int, set[int]] = {}

    def own_job_application(self, user_id: int, job_application_id: int) -> None:
        """Seed a job application the user owns, so an application resume may link it."""
        self._owned_job_applications.setdefault(user_id, set()).add(job_application_id)

    def bullet_refs(self, resume_id: int) -> list[int]:
        """The write-derived bullet-ref set for a resume (test inspection)."""
        return sorted(self._bullet_refs.get(resume_id, []))

    def revision(self, resume_id: int, revision_no: int) -> ResumeRevision | None:
        """A stored revision snapshot (test inspection)."""
        return self._revisions.get((resume_id, revision_no))

    def revision_count(self, resume_id: int) -> int:
        return sum(1 for resume_id_, _ in self._revisions if resume_id_ == resume_id)

    def seed(self, resume: Resume) -> Resume:
        """Insert a resume directly (sync test setup), minting an id if it has none."""
        if resume.id is None:
            resume.id = self._next_id
            self._next_id += 1
        if resume.revision is None:
            resume.revision = 1
        self._resumes[resume.id] = resume
        return resume

    async def add(self, resume: Resume) -> None:
        resume.id = self._next_id
        self._next_id += 1
        if resume.revision is None:
            resume.revision = 1
        self._resumes[resume.id] = resume

    async def get(self, user_id: int, resume_id: int) -> Resume | None:
        resume = self._resumes.get(resume_id)
        if resume is None or resume.user_id != user_id:
            return None
        return resume

    async def list_resumes(
        self, user_id: int, *, kind: ResumeKind | None, include_archived: bool, limit: int
    ) -> Sequence[Resume]:
        rows = [resume for resume in self._resumes.values() if resume.user_id == user_id]
        if kind is not None:
            rows = [resume for resume in rows if resume.kind is kind]
        if not include_archived:
            rows = [resume for resume in rows if resume.archived_at is None]
        rows.sort(key=lambda resume: resume.id, reverse=True)
        return rows[:limit]

    async def owned_job_application_ids(
        self, user_id: int, job_application_ids: Sequence[int]
    ) -> set[int]:
        return owned_from(self._owned_job_applications.get(user_id, set()), job_application_ids)

    async def job_application_link_exists(self, job_application_id: int) -> bool:
        return any(
            resume.job_application_id == job_application_id for resume in self._resumes.values()
        )

    async def set_bullet_refs(self, resume_id: int, bullet_ids: Sequence[int]) -> None:
        self._bullet_refs[resume_id] = list(bullet_ids)

    async def add_revision(self, revision: ResumeRevision) -> None:
        self._revisions[(revision.resume_id, revision.revision_no)] = revision

    async def ids_referencing_variant(self, user_id: int, variant_id: int) -> Sequence[int]:
        ids: list[int] = []
        for resume in self._resumes.values():
            if resume.user_id != user_id or resume.archived_at is not None:
                continue
            header = (resume.document or {}).get("header") or {}
            if header.get("identity_variant_id") == variant_id:
                ids.append(resume.id)
        return sorted(ids)

    async def used_in_count(self, bullet_id: int) -> int:
        return sum(bullet_id in refs for refs in self._bullet_refs.values())

    async def used_in_counts(self, bullet_ids: Sequence[int]) -> dict[int, int]:
        counts: dict[int, int] = {}
        for bullet_id in bullet_ids:
            count = sum(bullet_id in refs for refs in self._bullet_refs.values())
            if count:
                counts[bullet_id] = count
        return counts


class InMemoryBulletTextResolver:
    """A dict-backed :class:`BulletTextResolver`; only owned bullets resolve."""

    def __init__(self) -> None:
        self._texts: dict[tuple[int, int], str] = {}

    def own_bullet(self, user_id: int, bullet_id: int, text: str) -> None:
        """Seed a canonical bullet the user owns with its current text."""
        self._texts[(user_id, bullet_id)] = text

    async def resolve(self, user_id: int, bullet_ids: Sequence[int]) -> dict[int, str]:
        resolved: dict[int, str] = {}
        for bullet_id in bullet_ids:
            text = self._texts.get((user_id, bullet_id))
            if text is not None:
                resolved[bullet_id] = text
        return resolved


class LibraryRepoTextResolver:
    """A sociable :class:`BulletTextResolver` reading canonical text from the library repo.

    Copy-on-write and promote tests wire this over the same in-memory library
    repository the real :class:`LibraryCanonicalBulletWriter` writes to, so a bullet
    the writer creates or edits resolves for the resume snapshot exactly as it would
    against a shared Postgres, without a second seeded store to keep in sync.
    """

    def __init__(self, repo: InMemoryLibraryRepository) -> None:
        self._repo = repo

    async def resolve(self, user_id: int, bullet_ids: Sequence[int]) -> dict[int, str]:
        resolved: dict[int, str] = {}
        for bullet_id in bullet_ids:
            bullet = await self._repo.get(user_id, bullet_id)
            if bullet is not None:
                resolved[bullet_id] = bullet.text
        return resolved


def build_bullet_writer(
    session: AsyncSession,
    publisher: WriteEventPublisher,
    *,
    library_repo: InMemoryLibraryRepository | None = None,
) -> LibraryCanonicalBulletWriter:
    """The real canonical-bullet writer over an in-memory library repo.

    Tests that do not exercise copy-on-write pass this so the service has a writer
    it never calls; copy-on-write tests pass a shared ``library_repo`` (paired with
    :class:`LibraryRepoTextResolver`) so the writer's bullets resolve in snapshots.
    """
    return LibraryCanonicalBulletWriter(
        session, library_repo or InMemoryLibraryRepository(), publisher
    )


def build_create_request(**overrides: Any) -> ResumeCreateRequest:
    base: dict[str, Any] = {"kind": "living", "source": {"mode": "blank"}}
    base.update(overrides)
    return ResumeCreateRequest.model_validate(base)


def build_section(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "sec-work",
        "kind": "work",
        "title": "Experience",
        "item_order": [],
        "items": {},
    }
    base.update(overrides)
    return base


def build_update(**overrides: Any) -> ResumeUpdate:
    base: dict[str, Any] = {
        "title": "Backend Engineer",
        "template_id": "default",
        "header": {},
        "sections": [],
    }
    base.update(overrides)
    return ResumeUpdate.model_validate(base)


def build_add_item(**overrides: Any) -> AddItemRequest:
    base: dict[str, Any] = {
        "section_id": "sec-work",
        "item": {"kind": "local", "text": "Shipped the thing."},
    }
    base.update(overrides)
    return AddItemRequest.model_validate(base)
