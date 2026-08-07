"""Doubles and builders for the render/export path.

The render service is tested sociably: the real render module (over a fake Typst
compiler, or the real one where the test asserts PDF output) runs against these
in-memory doubles, which stand in only at true external boundaries: Postgres via the
in-memory render repository and identity resolver, R2 via the fake object store. The
builders assemble resolved documents (every item inline) so tests exercise the
mapper and the template without touching the write path.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from floresu.resumes.document import (
    IdentitySnapshot,
    IdentitySnapshotContact,
    IdentitySnapshotLink,
    LocalItem,
    ResumeDocument,
    ResumeHeader,
    ResumeSection,
    SectionKind,
)
from floresu.resumes.models import Resume, ResumeRevision

if TYPE_CHECKING:
    from collections.abc import Sequence


class FakeTypstCompiler:
    """Records compile calls and returns canned PDF bytes (no real Typst)."""

    def __init__(self, pdf: bytes = b"%PDF-1.7 fake") -> None:
        self._pdf = pdf
        self.calls: list[tuple[Path, Path, str]] = []

    def compile(self, entrypoint: Path, root: Path, data_json: str) -> bytes:
        self.calls.append((entrypoint, root, data_json))
        return self._pdf


class InMemoryRenderRepository:
    """A dict-backed :class:`RenderRepository` with real ids and ownership scoping."""

    def __init__(self) -> None:
        self._resumes: dict[int, Resume] = {}
        self._revisions: dict[int, list[ResumeRevision]] = {}
        self.pdf_keys: dict[tuple[int, int], str] = {}

    def seed_resume(self, resume: Resume) -> None:
        self._resumes[resume.id] = resume

    def seed_revision(self, revision: ResumeRevision) -> None:
        self._revisions.setdefault(revision.resume_id, []).append(revision)

    async def get_resume(self, user_id: int, resume_id: int) -> Resume | None:
        resume = self._resumes.get(resume_id)
        if resume is None or resume.user_id != user_id:
            return None
        return resume

    async def latest_revision(self, resume_id: int) -> ResumeRevision | None:
        revisions = self._revisions.get(resume_id)
        if not revisions:
            return None
        return max(revisions, key=lambda revision: revision.revision_no)

    async def set_revision_pdf_key(self, resume_id: int, revision_no: int, object_key: str) -> None:
        self.pdf_keys[(resume_id, revision_no)] = object_key
        for revision in self._revisions.get(resume_id, []):
            if revision.revision_no == revision_no:
                revision.pdf_object_key = object_key

    async def list_revisions_with_pdf(self, resume_id: int) -> Sequence[ResumeRevision]:
        stored = [
            revision
            for revision in self._revisions.get(resume_id, [])
            if revision.pdf_object_key is not None
        ]
        return sorted(stored, key=lambda revision: revision.revision_no, reverse=True)

    async def get_revision(self, resume_id: int, revision_no: int) -> ResumeRevision | None:
        for revision in self._revisions.get(resume_id, []):
            if revision.revision_no == revision_no:
                return revision
        return None


class InMemoryIdentityResolver:
    """A dict-backed :class:`IdentityResolver`: variants by id plus a per-user default."""

    def __init__(self) -> None:
        self._by_id: dict[tuple[int, int], IdentitySnapshot] = {}
        self._default: dict[int, IdentitySnapshot] = {}

    def own_variant(self, user_id: int, variant_id: int, snapshot: IdentitySnapshot) -> None:
        self._by_id[(user_id, variant_id)] = snapshot

    def set_default(self, user_id: int, snapshot: IdentitySnapshot) -> None:
        self._default[user_id] = snapshot

    async def resolve(self, user_id: int, variant_id: int | None) -> IdentitySnapshot | None:
        if variant_id is not None:
            found = self._by_id.get((user_id, variant_id))
            if found is not None:
                return found
        return self._default.get(user_id)


def build_snapshot(**overrides: Any) -> IdentitySnapshot:
    """A frozen identity snapshot for a resolved header."""
    base: dict[str, Any] = {
        "full_name": "Ada Lovelace",
        "contact": {"email": "ada@example.com", "phone": "+1 555 0100", "location": "London, UK"},
        "links": [{"label": "portfolio", "url": "https://ada.example.com"}],
    }
    base.update(overrides)
    return IdentitySnapshot.model_validate(base)


def local_section(section_id: str, kind: str, title: str, texts: list[str]) -> ResumeSection:
    """A section whose items are all inline local items (a resolved section)."""
    item_ids = [f"{section_id}-{index}" for index in range(len(texts))]
    return ResumeSection(
        id=section_id,
        kind=SectionKind(kind),
        title=title,
        item_order=item_ids,
        items={
            item_id: LocalItem(id=item_id, text=text)
            for item_id, text in zip(item_ids, texts, strict=True)
        },
    )


def build_resolved_document(
    *,
    snapshot: IdentitySnapshot | None = None,
    sections: list[ResumeSection] | None = None,
    template_id: str = "classic",
) -> ResumeDocument:
    """A fully resolved resume document (inline items, header snapshot set)."""
    if snapshot is None:
        snapshot = build_snapshot()
    if sections is None:
        sections = [
            local_section("s-sum", "summary", "Summary", ["First programmer; analytical engine."]),
            local_section(
                "s-work",
                "work",
                "Experience",
                ["Built the *first* algorithm.", "Cut latency 40%."],
            ),
        ]
    return ResumeDocument(
        schema_version=1,
        header=ResumeHeader(identity_snapshot=snapshot),
        template_id=template_id,
        sections=sections,
    )


def resume_row(*, resume_id: int, user_id: int, document: ResumeDocument) -> Resume:
    """A minimal ``resumes`` row carrying a document (the render repo reads these)."""
    return Resume(id=resume_id, user_id=user_id, document=document.model_dump(mode="json"))


def revision_row(
    *,
    resume_id: int,
    revision_no: int,
    document: ResumeDocument,
    pdf_object_key: str | None = None,
    created_at: datetime | None = None,
) -> ResumeRevision:
    """A minimal ``resume_revisions`` row carrying a resolved snapshot document.

    ``pdf_object_key`` marks the revision as a published version (an export or a
    finalize stored its PDF); ``created_at`` stamps the snapshot for the
    newest-first history list (the DB server-defaults it on a real insert).
    """
    return ResumeRevision(
        resume_id=resume_id,
        revision_no=revision_no,
        document=document.model_dump(mode="json"),
        schema_version=document.schema_version,
        pdf_object_key=pdf_object_key,
        created_at=created_at,
    )


__all__ = [
    "FakeTypstCompiler",
    "IdentitySnapshotContact",
    "IdentitySnapshotLink",
    "InMemoryIdentityResolver",
    "InMemoryRenderRepository",
    "build_resolved_document",
    "build_snapshot",
    "local_section",
    "resume_row",
    "revision_row",
]
