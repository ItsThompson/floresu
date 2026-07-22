"""End-to-end revision-history tests against real Postgres with a fake R2 store.

Runs the real :class:`ResumeRevisionService` over the SQLAlchemy render repository
against real Postgres, minting URLs through a fake object store. It seeds published
versions the way the product does (an export records ``pdf_object_key`` on a
revision) and proves the list returns only revisions with a stored PDF newest-first,
that a per-version request mints a presigned URL, that an unpublished or missing
revision is a recoverable 404, and that another account's resume is a 404. External
R2 is faked; no live credentials are used.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config

from floresu.accounts.models import User
from floresu.audit.wiring import build_write_event_publisher
from floresu.core.actor import Actor, ActorType
from floresu.core.db import create_db_engine, create_sessionmaker, transaction
from floresu.core.errors import NotFound
from floresu.library.cow import LibraryCanonicalBulletWriter
from floresu.library.repository import SqlAlchemyLibraryRepository
from floresu.rendering.module import RenderModule
from floresu.rendering.typst import TypstPyCompiler
from floresu.resumes.document import LocalItem, ResumeHeader, ResumeSection, SectionKind
from floresu.resumes.identity_resolver import SqlAlchemyIdentityResolver
from floresu.resumes.models import ResumeKind
from floresu.resumes.render_repository import SqlAlchemyRenderRepository
from floresu.resumes.render_service import ResumeRenderService
from floresu.resumes.repository import SqlAlchemyResumeRepository
from floresu.resumes.resolver import SqlAlchemyBulletTextResolver
from floresu.resumes.revision_service import ResumeRevisionService
from floresu.resumes.schemas import BlankSource, ResumeCreateRequest, ResumeUpdate
from floresu.resumes.service import ResumeService
from tests.storage_fakes import FakeObjectStore

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]
_HUMAN = Actor(type=ActorType.HUMAN)


@pytest.fixture
def migrated_url(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")
    return postgres_url


async def _insert_user(sessionmaker: async_sessionmaker[AsyncSession], email: str) -> int:
    async with sessionmaker() as session, transaction(session):
        user = User(email=email, password_hash="x")
        session.add(user)
        await session.flush()
        return user.id


async def _create_resume_with_content(
    sessionmaker: async_sessionmaker[AsyncSession], user_id: int
) -> int:
    """Create a living resume and give it one content update (revision 2)."""
    async with sessionmaker() as session:
        publisher = build_write_event_publisher()
        service = ResumeService(
            session,
            SqlAlchemyResumeRepository(session),
            SqlAlchemyBulletTextResolver(session),
            publisher,
            LibraryCanonicalBulletWriter(session, SqlAlchemyLibraryRepository(session), publisher),
        )
        created = await service.create(
            str(user_id), _HUMAN, ResumeCreateRequest(kind=ResumeKind.LIVING, source=BlankSource())
        )
        await service.update(
            str(user_id),
            created.id,
            _HUMAN,
            created.revision,
            ResumeUpdate(
                title="Backend Engineer",
                template_id="classic",
                header=ResumeHeader(identity_variant_id=None),
                sections=[
                    ResumeSection(
                        id="s-work",
                        kind=SectionKind.WORK,
                        title="Experience",
                        item_order=["a"],
                        items={"a": LocalItem(id="a", text="Owned the search relaunch.")},
                    )
                ],
            ),
        )
        return created.id


async def _export(
    sessionmaker: async_sessionmaker[AsyncSession],
    store: FakeObjectStore,
    user_id: int,
    resume_id: int,
) -> None:
    """Render + persist the latest revision, recording ``pdf_object_key`` on it."""
    async with sessionmaker() as session:
        service = ResumeRenderService(
            session,
            SqlAlchemyRenderRepository(session),
            SqlAlchemyBulletTextResolver(session),
            SqlAlchemyIdentityResolver(session),
            RenderModule(TypstPyCompiler()),
            store,
            build_write_event_publisher(),
        )
        await service.export(str(user_id), resume_id, _HUMAN)


def _revision_service(session: AsyncSession, store: FakeObjectStore) -> ResumeRevisionService:
    return ResumeRevisionService(SqlAlchemyRenderRepository(session), store)


async def test_list_returns_only_the_exported_revision(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "revision-list@example.com")
        resume_id = await _create_resume_with_content(sessionmaker, user_id)
        store = FakeObjectStore()
        # Only revision 2 is exported; revision 1 (from create) has no stored PDF.
        await _export(sessionmaker, store, user_id, resume_id)

        async with sessionmaker() as session:
            result = await _revision_service(session, store).list_published_versions(
                str(user_id), resume_id
            )

        assert result.resume_id == resume_id
        assert [version.revision_no for version in result.versions] == [2]
        assert result.versions[0].created_at is not None
    finally:
        await engine.dispose()


async def test_version_pdf_url_mints_a_url_for_the_stored_revision(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "revision-pdf@example.com")
        resume_id = await _create_resume_with_content(sessionmaker, user_id)
        store = FakeObjectStore()
        await _export(sessionmaker, store, user_id, resume_id)

        async with sessionmaker() as session:
            result = await _revision_service(session, store).version_pdf_url(
                str(user_id), resume_id, 2
            )

        expected_key = f"u/{user_id}/r/{resume_id}/rev/2.pdf"
        assert result.revision_no == 2
        assert result.download_url.endswith(f"{expected_key}?signed=1")
    finally:
        await engine.dispose()


async def test_unpublished_and_missing_revisions_are_recoverable_404s(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "revision-404@example.com")
        resume_id = await _create_resume_with_content(sessionmaker, user_id)
        store = FakeObjectStore()
        await _export(sessionmaker, store, user_id, resume_id)

        async with sessionmaker() as session:
            service = _revision_service(session, store)
            with pytest.raises(NotFound):
                await service.version_pdf_url(str(user_id), resume_id, 1)  # exists, no stored PDF
            with pytest.raises(NotFound):
                await service.version_pdf_url(str(user_id), resume_id, 99)  # does not exist
    finally:
        await engine.dispose()


async def test_another_accounts_resume_is_a_404(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        owner_id = await _insert_user(sessionmaker, "revision-owner@example.com")
        other_id = await _insert_user(sessionmaker, "revision-other@example.com")
        resume_id = await _create_resume_with_content(sessionmaker, owner_id)
        store = FakeObjectStore()
        await _export(sessionmaker, store, owner_id, resume_id)

        async with sessionmaker() as session:
            service = _revision_service(session, store)
            with pytest.raises(NotFound):
                await service.list_published_versions(str(other_id), resume_id)
            with pytest.raises(NotFound):
                await service.version_pdf_url(str(other_id), resume_id, 2)
    finally:
        await engine.dispose()


async def test_a_resume_with_no_export_lists_no_versions(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "revision-empty@example.com")
        resume_id = await _create_resume_with_content(sessionmaker, user_id)
        store = FakeObjectStore()
        # No export: no revision has a stored PDF.
        async with sessionmaker() as session:
            result = await _revision_service(session, store).list_published_versions(
                str(user_id), resume_id
            )

        assert result.versions == []
    finally:
        await engine.dispose()
