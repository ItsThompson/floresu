"""ResumeRevisionService: list published versions and mint a URL for one's PDF.

Sociable tests: the real service runs against in-memory doubles at the true
boundaries (Postgres via the render repo, R2 via the fake object store). They assert
the stored-PDF filter (a per-save revision with no PDF is never listed), newest-first
order, the empty list for a resume with no published version, the presigned URL minted
via the store, that a missing or unpublished revision is a recoverable 404, and that
another account's resume is a 404 on both reads with no existence leak.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from floresu.core.errors import NotFound, Unauthorized
from floresu.resumes.revision_service import ResumeRevisionService
from tests.rendering_fakes import (
    InMemoryRenderRepository,
    build_resolved_document,
    resume_row,
    revision_row,
)
from tests.storage_fakes import FakeObjectStore


class _Harness:
    def __init__(
        self, service: ResumeRevisionService, repo: InMemoryRenderRepository, store: FakeObjectStore
    ) -> None:
        self.service = service
        self.repo = repo
        self.store = store

    def seed_resume(self, *, resume_id: int, user_id: int) -> None:
        self.repo.seed_resume(
            resume_row(resume_id=resume_id, user_id=user_id, document=build_resolved_document())
        )

    def seed_revision(
        self,
        *,
        resume_id: int,
        revision_no: int,
        pdf_object_key: str | None,
        created_at: datetime | None = None,
    ) -> None:
        self.repo.seed_revision(
            revision_row(
                resume_id=resume_id,
                revision_no=revision_no,
                document=build_resolved_document(),
                pdf_object_key=pdf_object_key,
                created_at=created_at or datetime(2026, 1, revision_no, tzinfo=UTC),
            )
        )


def _harness() -> _Harness:
    repo = InMemoryRenderRepository()
    store = FakeObjectStore()
    return _Harness(ResumeRevisionService(repo, store), repo, store)


async def test_list_returns_only_published_versions_newest_first() -> None:
    h = _harness()
    h.seed_resume(resume_id=7, user_id=1)
    h.seed_revision(resume_id=7, revision_no=3, pdf_object_key="u/1/r/7/rev/3.pdf")
    h.seed_revision(resume_id=7, revision_no=2, pdf_object_key=None)  # a plain per-save snapshot
    h.seed_revision(resume_id=7, revision_no=5, pdf_object_key="u/1/r/7/rev/5.pdf")

    result = await h.service.list_published_versions("1", 7)

    assert result.resume_id == 7
    # Newest first, and the pdf_object_key-less revision 2 is excluded.
    assert [version.revision_no for version in result.versions] == [5, 3]


async def test_list_carries_the_revision_timestamp() -> None:
    h = _harness()
    h.seed_resume(resume_id=7, user_id=1)
    stamped = datetime(2026, 7, 4, 12, 30, tzinfo=UTC)
    h.seed_revision(resume_id=7, revision_no=4, pdf_object_key="k", created_at=stamped)

    result = await h.service.list_published_versions("1", 7)

    assert result.versions[0].created_at == stamped


async def test_list_is_empty_for_a_resume_with_no_published_version() -> None:
    h = _harness()
    h.seed_resume(resume_id=7, user_id=1)
    h.seed_revision(resume_id=7, revision_no=1, pdf_object_key=None)

    result = await h.service.list_published_versions("1", 7)

    assert result.versions == []  # empty, not an error


async def test_list_missing_resume_is_not_found() -> None:
    h = _harness()
    with pytest.raises(NotFound):
        await h.service.list_published_versions("1", 404)


async def test_list_another_accounts_resume_is_not_found() -> None:
    h = _harness()
    h.seed_resume(resume_id=7, user_id=2)  # owned by another account
    h.seed_revision(resume_id=7, revision_no=1, pdf_object_key="k")

    with pytest.raises(NotFound):
        await h.service.list_published_versions("1", 7)


async def test_version_pdf_url_mints_a_presigned_url_for_the_stored_object() -> None:
    h = _harness()
    h.seed_resume(resume_id=7, user_id=1)
    h.seed_revision(resume_id=7, revision_no=3, pdf_object_key="u/1/r/7/rev/3.pdf")

    result = await h.service.version_pdf_url("1", 7, 3)

    assert result.resume_id == 7
    assert result.revision_no == 3
    assert result.download_url == "https://fake-r2.local/u/1/r/7/rev/3.pdf?signed=1"
    # The R2 object key is never on the wire: the schema carries only the URL.
    assert "object_key" not in result.model_dump()


async def test_version_pdf_url_missing_revision_is_a_recoverable_not_found() -> None:
    h = _harness()
    h.seed_resume(resume_id=7, user_id=1)

    with pytest.raises(NotFound):
        await h.service.version_pdf_url("1", 7, 99)


async def test_version_pdf_url_unpublished_revision_is_not_found() -> None:
    h = _harness()
    h.seed_resume(resume_id=7, user_id=1)
    h.seed_revision(resume_id=7, revision_no=2, pdf_object_key=None)

    with pytest.raises(NotFound):
        await h.service.version_pdf_url("1", 7, 2)


async def test_version_pdf_url_another_accounts_resume_is_not_found() -> None:
    h = _harness()
    h.seed_resume(resume_id=7, user_id=2)
    h.seed_revision(resume_id=7, revision_no=1, pdf_object_key="k")

    with pytest.raises(NotFound):
        await h.service.version_pdf_url("1", 7, 1)


async def test_an_invalid_identity_is_unauthorized() -> None:
    h = _harness()
    with pytest.raises(Unauthorized):
        await h.service.list_published_versions("not-an-int", 7)
