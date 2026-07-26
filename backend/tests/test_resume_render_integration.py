"""End-to-end render tests against real Postgres: resolution, preview, and export.

Runs the real :class:`ResumeRenderService` over the SQLAlchemy render repository,
bullet-text resolver, and identity resolver, the real render module (in-process
typst-py + the committed classic template), and a fake object store. It proves a
saved resume resolves (references to text, the identity variant to a header
snapshot) and renders to a PDF with selectable text, and that export persists to the
store under the revision-keyed object key and records that key on the revision row in
Postgres. External R2 is faked; no live credentials are used.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from pypdf import PdfReader
from sqlalchemy import select

from floresu.accounts.models import User
from floresu.audit.wiring import build_write_event_publisher
from floresu.core.actor import Actor, ActorType
from floresu.core.db import create_db_engine, create_sessionmaker, transaction
from floresu.library.cow import LibraryCanonicalBulletWriter
from floresu.library.repository import SqlAlchemyLibraryRepository
from floresu.profile.variants.repository import SqlAlchemyIdentityVariantRepository
from floresu.profile.variants.schemas import IdentityVariantWrite, VariantContact, VariantLink
from floresu.profile.variants.service import IdentityVariantService
from floresu.rendering.module import RenderModule
from floresu.rendering.typst import TypstPyCompiler
from floresu.resumes.document import LocalItem, ResumeHeader, ResumeSection, SectionKind
from floresu.resumes.identity_resolver import SqlAlchemyIdentityResolver
from floresu.resumes.models import ResumeKind, ResumeRevision
from floresu.resumes.render_repository import SqlAlchemyRenderRepository
from floresu.resumes.render_service import ResumeRenderService
from floresu.resumes.repository import SqlAlchemyResumeRepository
from floresu.resumes.resolver import SqlAlchemyBulletTextResolver
from floresu.resumes.schemas import BlankSource, ResumeCreateRequest, ResumeUpdate
from floresu.resumes.service import ResumeService
from floresu.resumes.wiring import build_resume_service
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


async def _create_default_variant(
    sessionmaker: async_sessionmaker[AsyncSession], user_id: int
) -> int:
    async with sessionmaker() as session:
        publisher = build_write_event_publisher()
        service = IdentityVariantService(
            session,
            SqlAlchemyIdentityVariantRepository(session),
            publisher,
            build_resume_service(session, publisher),
        )
        record = await service.create(
            str(user_id),
            _HUMAN,
            IdentityVariantWrite(
                label="Primary",
                full_name="Ada Lovelace",
                contact=VariantContact(email="ada@example.com", location="London, UK"),
                links=[VariantLink(label="portfolio", url="https://ada.example.com")],
                is_default=True,
            ),
        )
        return record.id


async def _create_resume_with_content(
    sessionmaker: async_sessionmaker[AsyncSession],
    user_id: int,
    *,
    variant_id: int | None,
    bullet_text: str,
) -> int:
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
                header=ResumeHeader(identity_variant_id=variant_id),
                sections=[
                    ResumeSection(
                        id="s-work",
                        kind=SectionKind.WORK,
                        title="Experience",
                        item_order=["a"],
                        items={"a": LocalItem(id="a", text=bullet_text)},
                    )
                ],
            ),
        )
        return created.id


def _render_service(session: AsyncSession, store: FakeObjectStore) -> ResumeRenderService:
    return ResumeRenderService(
        session,
        SqlAlchemyRenderRepository(session),
        SqlAlchemyBulletTextResolver(session),
        SqlAlchemyIdentityResolver(session),
        RenderModule(TypstPyCompiler()),
        store,
        build_write_event_publisher(),
    )


def _extract_text(pdf: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf))
    return "\n".join(page.extract_text() for page in reader.pages)


async def test_preview_resolves_the_variant_by_id_and_renders_selectable_text(
    migrated_url: str,
) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "render-preview@example.com")
        variant_id = await _create_default_variant(sessionmaker, user_id)
        resume_id = await _create_resume_with_content(
            sessionmaker, user_id, variant_id=variant_id, bullet_text="Led the Postgres migration."
        )
        store = FakeObjectStore()
        async with sessionmaker() as session:
            pdf = await _render_service(session, store).preview(str(user_id), resume_id)

        assert pdf.startswith(b"%PDF")
        text = _extract_text(pdf)
        assert "Ada Lovelace" in text
        assert "Postgres migration" in text
        assert store.objects == {}  # preview never persists
    finally:
        await engine.dispose()


async def test_export_persists_the_pdf_and_records_the_object_key(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "render-export@example.com")
        # No variant referenced on the header: the resolver falls back to the default.
        await _create_default_variant(sessionmaker, user_id)
        resume_id = await _create_resume_with_content(
            sessionmaker, user_id, variant_id=None, bullet_text="Owned the search relaunch."
        )
        store = FakeObjectStore()
        async with sessionmaker() as session:
            result = await _render_service(session, store).export(str(user_id), resume_id, _HUMAN)

        # The revision after create + one update is 2; the key is revision-scoped.
        expected_key = f"u/{user_id}/r/{resume_id}/rev/2.pdf"
        assert result.object_key == expected_key
        assert result.revision == 2
        assert expected_key in store.objects
        stored_bytes, content_type = store.objects[expected_key]
        assert stored_bytes.startswith(b"%PDF")
        assert content_type == "application/pdf"
        assert "Owned the search relaunch." in _extract_text(stored_bytes)

        # The object key is recorded on the revision row in Postgres.
        async with sessionmaker() as session:
            recorded = await session.execute(
                select(ResumeRevision.pdf_object_key).where(
                    ResumeRevision.resume_id == resume_id, ResumeRevision.revision_no == 2
                )
            )
            assert recorded.scalar_one() == expected_key
    finally:
        await engine.dispose()


async def test_preview_renders_an_empty_header_when_no_identity_resolves(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "render-noident@example.com")
        # No identity variant exists, and the resume references none: the resolver
        # returns nothing and the header renders empty (the template omits the lines).
        resume_id = await _create_resume_with_content(
            sessionmaker, user_id, variant_id=None, bullet_text="Shipped without an identity set."
        )
        store = FakeObjectStore()
        async with sessionmaker() as session:
            pdf = await _render_service(session, store).preview(str(user_id), resume_id)

        assert pdf.startswith(b"%PDF")
        assert "Shipped without an identity set." in _extract_text(pdf)
    finally:
        await engine.dispose()
