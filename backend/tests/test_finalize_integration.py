"""End-to-end finalize + job-application lifecycle against real Postgres.

Runs the real :class:`ResumeFinalizeService` and :class:`JobApplicationService` over
the SQLAlchemy repositories, the real bullet-text and identity resolvers, the real
render module (fake Typst compiler), a fake R2 store, and the composed write-event
publisher (audit as its transactional consumer). Proves the finalize contract against
real SQL: references freeze to inline text (zero ``library_ref`` remain), the identity
snapshots inline, the frozen PDF is stored with its key on the appended revision, the
resume drops out of "used in N", a later library edit cannot change it, and it becomes
read-only. The submit=finalize convergence is exercised both directions, and a submit
with no linked resume is rejected while the status stays ``added``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from floresu.accounts.models import User
from floresu.audit.models import AuditLog
from floresu.audit.wiring import build_write_event_publisher
from floresu.core.actor import Actor, ActorType
from floresu.core.db import create_db_engine, create_sessionmaker, transaction
from floresu.core.errors import Conflict
from floresu.jobapps.repository import SqlAlchemyJobApplicationRepository
from floresu.jobapps.schemas import JobApplicationUpdate
from floresu.jobapps.service import JobApplicationService
from floresu.library.cow import LibraryCanonicalBulletWriter
from floresu.library.repository import SqlAlchemyLibraryRepository
from floresu.library.schemas import BulletpointWrite
from floresu.library.service import LibraryService
from floresu.profile.variants.models import IdentityVariant
from floresu.rendering.module import RenderModule
from floresu.resumes.document import LocalItem
from floresu.resumes.finalize import ResumeFinalizeService
from floresu.resumes.identity_resolver import SqlAlchemyIdentityResolver
from floresu.resumes.models import (
    JobApplication,
    JobApplicationStatus,
    Resume,
    ResumeBulletRef,
    ResumeRevision,
    ResumeStatus,
)
from floresu.resumes.repository import SqlAlchemyResumeRepository
from floresu.resumes.resolver import SqlAlchemyBulletTextResolver
from floresu.resumes.schemas import ResumeCreateRequest, ResumeUpdate
from floresu.resumes.service import ResumeService
from tests.rendering_fakes import FakeTypstCompiler
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


async def _insert_job_application(
    sessionmaker: async_sessionmaker[AsyncSession], user_id: int
) -> int:
    async with sessionmaker() as session, transaction(session):
        application = JobApplication(user_id=user_id, company="Acme", role_title="Backend Engineer")
        session.add(application)
        await session.flush()
        return application.id


async def _insert_variant(sessionmaker: async_sessionmaker[AsyncSession], user_id: int) -> int:
    async with sessionmaker() as session, transaction(session):
        variant = IdentityVariant(
            user_id=user_id,
            label="Default",
            full_name="Ada Lovelace",
            contact={"email": "ada@example.com", "phone": None, "location": "London, UK"},
            links=[],
            is_default=True,
        )
        session.add(variant)
        await session.flush()
        return variant.id


async def _create_bullet(
    sessionmaker: async_sessionmaker[AsyncSession], user_id: int, text: str
) -> int:
    async with sessionmaker() as session:
        service = LibraryService(
            session,
            SqlAlchemyLibraryRepository(session),
            build_write_event_publisher(),
            SqlAlchemyResumeRepository(session),
        )
        record = await service.create(str(user_id), _HUMAN, BulletpointWrite(text=text))
        return record.id


async def _edit_bullet(
    sessionmaker: async_sessionmaker[AsyncSession], user_id: int, bullet_id: int, text: str
) -> None:
    async with sessionmaker() as session:
        service = LibraryService(
            session,
            SqlAlchemyLibraryRepository(session),
            build_write_event_publisher(),
            SqlAlchemyResumeRepository(session),
        )
        current = await service.get(str(user_id), bullet_id)
        await service.update(
            str(user_id), bullet_id, _HUMAN, BulletpointWrite(text=text), current.revision
        )


def _resumes(session: AsyncSession) -> ResumeService:
    publisher = build_write_event_publisher()
    return ResumeService(
        session,
        SqlAlchemyResumeRepository(session),
        SqlAlchemyBulletTextResolver(session),
        publisher,
        LibraryCanonicalBulletWriter(session, SqlAlchemyLibraryRepository(session), publisher),
    )


def _finalizer(session: AsyncSession, store: FakeObjectStore) -> ResumeFinalizeService:
    return ResumeFinalizeService(
        session,
        SqlAlchemyResumeRepository(session),
        SqlAlchemyBulletTextResolver(session),
        SqlAlchemyIdentityResolver(session),
        RenderModule(FakeTypstCompiler(), templates_dir=Path("/tmpl")),
        store,
        SqlAlchemyJobApplicationRepository(session),
        build_write_event_publisher(),
    )


def _jobapps(session: AsyncSession, store: FakeObjectStore) -> JobApplicationService:
    return JobApplicationService(
        session,
        SqlAlchemyJobApplicationRepository(session),
        build_write_event_publisher(),
        _finalizer(session, store),
    )


def _ref_section(bullet_id: int) -> dict[str, object]:
    return {
        "id": "sec-work",
        "kind": "work",
        "title": "Experience",
        "item_order": ["a"],
        "items": {"a": {"id": "a", "kind": "library_ref", "bullet_id": bullet_id}},
    }


async def _application_resume_with_ref(
    sessionmaker: async_sessionmaker[AsyncSession],
    user_id: int,
    application_id: int,
    bullet_id: int,
    variant_id: int,
) -> int:
    """Create an application draft linked to the job application, referencing one bullet."""
    async with sessionmaker() as session:
        created = await _resumes(session).create(
            str(user_id),
            _HUMAN,
            ResumeCreateRequest.model_validate(
                {
                    "kind": "application",
                    "source": {"mode": "blank"},
                    "job_application_id": application_id,
                }
            ),
        )
    async with sessionmaker() as session:
        await _resumes(session).update(
            str(user_id),
            created.id,
            _HUMAN,
            created.revision,
            ResumeUpdate.model_validate(
                {
                    "title": "Backend Engineer",
                    "template_id": "classic",
                    "header": {"identity_variant_id": variant_id},
                    "sections": [_ref_section(bullet_id)],
                }
            ),
        )
    return created.id


async def test_direct_finalize_freezes_the_resume_and_stores_the_pdf(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    store = FakeObjectStore()
    try:
        user_id = await _insert_user(sessionmaker, "fin-direct@example.com")
        application_id = await _insert_job_application(sessionmaker, user_id)
        variant_id = await _insert_variant(sessionmaker, user_id)
        bullet_id = await _create_bullet(sessionmaker, user_id, "Shipped the pipeline.")
        resume_id = await _application_resume_with_ref(
            sessionmaker, user_id, application_id, bullet_id, variant_id
        )

        async with sessionmaker() as session:
            result = await _finalizer(session, store).finalize(str(user_id), resume_id, _HUMAN)

        async with sessionmaker() as session:
            resume = await session.get(Resume, resume_id)
            assert resume is not None
            document = resume.document
            items = document["sections"][0]["items"]
            application = await session.get(JobApplication, application_id)
            ref_count = await session.scalar(
                select(func.count())
                .select_from(ResumeBulletRef)
                .where(ResumeBulletRef.bullet_id == bullet_id)
            )
            snapshot = await session.get(ResumeRevision, (resume_id, result.revision_no))
            action_rows = (
                await session.execute(
                    select(AuditLog.entity_type, AuditLog.action).where(AuditLog.user_id == user_id)
                )
            ).all()
            actions = {(row[0], row[1]) for row in action_rows}
    finally:
        await engine.dispose()

    assert result.status is ResumeStatus.FINALIZED
    assert result.pdf_object_key in store.objects
    assert resume.status == ResumeStatus.FINALIZED.value
    # Every item is inline local text; zero references remain.
    assert all(item["kind"] == "local" for item in items.values())
    assert items["a"]["text"] == "Shipped the pipeline."
    assert items["a"]["forked_from_bullet_id"] == bullet_id
    assert document["header"]["identity_snapshot"]["full_name"] == "Ada Lovelace"
    assert document["header"]["identity_variant_id"] is None
    # The resume dropped out of "used in N".
    assert ref_count == 0
    # A frozen revision snapshot carries the PDF key and zero references.
    assert snapshot is not None
    assert snapshot.pdf_object_key == result.pdf_object_key
    assert all(
        item["kind"] == "local"
        for section in snapshot.document["sections"]
        for item in section["items"].values()
    )
    # The linked application is submitted and both writes are audited.
    assert application is not None
    assert application.status == JobApplicationStatus.SUBMITTED.value
    assert ("resume", "finalize") in actions
    assert ("job_application", "update") in actions


async def test_finalized_resume_is_immune_to_a_later_library_edit(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    store = FakeObjectStore()
    try:
        user_id = await _insert_user(sessionmaker, "fin-immune@example.com")
        application_id = await _insert_job_application(sessionmaker, user_id)
        variant_id = await _insert_variant(sessionmaker, user_id)
        bullet_id = await _create_bullet(sessionmaker, user_id, "Original frozen text.")
        resume_id = await _application_resume_with_ref(
            sessionmaker, user_id, application_id, bullet_id, variant_id
        )
        async with sessionmaker() as session:
            await _finalizer(session, store).finalize(str(user_id), resume_id, _HUMAN)

        await _edit_bullet(sessionmaker, user_id, bullet_id, "Edited after finalize.")

        async with sessionmaker() as session:
            record = await _resumes(session).get(str(user_id), resume_id)
    finally:
        await engine.dispose()

    item = record.document.sections[0].items["a"]
    assert isinstance(item, LocalItem)
    assert item.text == "Original frozen text."


async def test_marking_submitted_finalizes_the_linked_resume(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    store = FakeObjectStore()
    try:
        user_id = await _insert_user(sessionmaker, "fin-submit@example.com")
        application_id = await _insert_job_application(sessionmaker, user_id)
        variant_id = await _insert_variant(sessionmaker, user_id)
        bullet_id = await _create_bullet(sessionmaker, user_id, "Led the migration.")
        resume_id = await _application_resume_with_ref(
            sessionmaker, user_id, application_id, bullet_id, variant_id
        )

        async with sessionmaker() as session:
            summary = await _jobapps(session, store).update(
                str(user_id),
                _HUMAN,
                application_id,
                JobApplicationUpdate(status=JobApplicationStatus.SUBMITTED),
            )

        async with sessionmaker() as session:
            resume = await session.get(Resume, resume_id)
    finally:
        await engine.dispose()

    assert summary.status is JobApplicationStatus.SUBMITTED
    assert resume is not None
    assert resume.status == ResumeStatus.FINALIZED.value


async def test_submit_without_linked_resume_is_rejected_and_stays_added(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    store = FakeObjectStore()
    try:
        user_id = await _insert_user(sessionmaker, "fin-noresume@example.com")
        application_id = await _insert_job_application(sessionmaker, user_id)

        async with sessionmaker() as session:
            with pytest.raises(Conflict):
                await _jobapps(session, store).update(
                    str(user_id),
                    _HUMAN,
                    application_id,
                    JobApplicationUpdate(status=JobApplicationStatus.SUBMITTED),
                )

        async with sessionmaker() as session:
            application = await session.get(JobApplication, application_id)
    finally:
        await engine.dispose()

    assert application is not None
    assert application.status == JobApplicationStatus.ADDED.value


async def test_finalized_resume_is_read_only(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    store = FakeObjectStore()
    try:
        user_id = await _insert_user(sessionmaker, "fin-readonly@example.com")
        application_id = await _insert_job_application(sessionmaker, user_id)
        variant_id = await _insert_variant(sessionmaker, user_id)
        bullet_id = await _create_bullet(sessionmaker, user_id, "Frozen bullet.")
        resume_id = await _application_resume_with_ref(
            sessionmaker, user_id, application_id, bullet_id, variant_id
        )
        async with sessionmaker() as session:
            result = await _finalizer(session, store).finalize(str(user_id), resume_id, _HUMAN)

        async with sessionmaker() as session:
            with pytest.raises(Conflict):
                await _resumes(session).update(
                    str(user_id),
                    resume_id,
                    _HUMAN,
                    result.revision_no,
                    ResumeUpdate.model_validate(
                        {"title": "Nope", "template_id": "classic", "header": {}, "sections": []}
                    ),
                )
    finally:
        await engine.dispose()


async def test_finalize_remaps_a_revision_pk_race_to_a_recoverable_conflict(
    migrated_url: str,
) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    store = FakeObjectStore()
    try:
        user_id = await _insert_user(sessionmaker, "fin-race@example.com")
        application_id = await _insert_job_application(sessionmaker, user_id)
        variant_id = await _insert_variant(sessionmaker, user_id)
        bullet_id = await _create_bullet(sessionmaker, user_id, "Raced bullet.")
        resume_id = await _application_resume_with_ref(
            sessionmaker, user_id, application_id, bullet_id, variant_id
        )
        # Simulate a writer that committed the next revision first (a concurrent draft
        # edit or a double-submit), so finalize's snapshot insert collides on the
        # (resume_id, revision_no) PK.
        async with sessionmaker() as session, transaction(session):
            resume = await session.get(Resume, resume_id)
            assert resume is not None
            session.add(
                ResumeRevision(
                    resume_id=resume_id,
                    revision_no=resume.revision + 1,
                    document={"schema_version": 1, "template_id": "classic", "sections": []},
                    schema_version=1,
                )
            )

        async with sessionmaker() as session:
            with pytest.raises(Conflict):
                await _finalizer(session, store).finalize(str(user_id), resume_id, _HUMAN)
    finally:
        await engine.dispose()
