"""End-to-end job-application CRUD against real Postgres.

Exercises the real :class:`JobApplicationService` over the SQLAlchemy repository so the
create/list/get reads run against real SQL: an application starts ``added``, the list is
newest-first with the 1:1 resume link resolved off ``resumes.job_application_id``, get
resolves the link, and a plain field edit changes the row without finalizing. The
submit=finalize convergence and its rejections live in ``test_finalize_integration``.
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
from floresu.jobapps.repository import SqlAlchemyJobApplicationRepository
from floresu.jobapps.schemas import JobApplicationCreate, JobApplicationUpdate
from floresu.jobapps.service import JobApplicationService
from floresu.rendering.module import RenderModule
from floresu.resumes.finalize_wiring import build_resume_finalizer
from floresu.resumes.models import JobApplicationStatus, Resume, ResumeKind, ResumeStatus
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


def _jobapps(session: AsyncSession) -> JobApplicationService:
    publisher = build_write_event_publisher()
    finalizer = build_resume_finalizer(
        session,
        publisher,
        RenderModule(FakeTypstCompiler(), templates_dir=Path("/tmpl")),
        FakeObjectStore(),
    )
    return JobApplicationService(
        session, SqlAlchemyJobApplicationRepository(session), publisher, finalizer
    )


async def _link_resume(
    sessionmaker: async_sessionmaker[AsyncSession], user_id: int, application_id: int
) -> int:
    async with sessionmaker() as session, transaction(session):
        resume = Resume(
            user_id=user_id,
            kind=ResumeKind.APPLICATION,
            status=ResumeStatus.DRAFT,
            title="Backend Engineer",
            schema_version=1,
            revision=1,
            document={"schema_version": 1, "template_id": "classic", "sections": []},
            job_application_id=application_id,
        )
        session.add(resume)
        await session.flush()
        return resume.id


async def test_create_list_get_expose_status_and_linked_resume(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "japp-crud@example.com")
        async with sessionmaker() as session:
            first = await _jobapps(session).create(
                str(user_id), _HUMAN, JobApplicationCreate(company="Aperture", role_title="SWE")
            )
        async with sessionmaker() as session:
            second = await _jobapps(session).create(
                str(user_id), _HUMAN, JobApplicationCreate(company="Globex", role_title="Staff")
            )
        resume_id = await _link_resume(sessionmaker, user_id, first.id)

        async with sessionmaker() as session:
            listed = await _jobapps(session).list_applications(str(user_id))
        async with sessionmaker() as session:
            fetched = await _jobapps(session).get(str(user_id), first.id)
    finally:
        await engine.dispose()

    assert first.status is JobApplicationStatus.ADDED
    # Newest-first, with the 1:1 resume link resolved for the linked application only.
    assert [summary.id for summary in listed] == [second.id, first.id]
    links = {summary.id: summary.linked_resume_id for summary in listed}
    assert links == {first.id: resume_id, second.id: None}
    assert fetched.linked_resume_id == resume_id


async def test_update_company_edits_the_row_without_finalizing(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "japp-edit@example.com")
        async with sessionmaker() as session:
            created = await _jobapps(session).create(
                str(user_id), _HUMAN, JobApplicationCreate(company="Old", role_title="SWE")
            )
        async with sessionmaker() as session:
            updated = await _jobapps(session).update(
                str(user_id),
                _HUMAN,
                created.id,
                JobApplicationUpdate(company="New", role_title="Staff Engineer"),
            )
    finally:
        await engine.dispose()

    assert updated.company == "New"
    assert updated.role_title == "Staff Engineer"
    assert updated.status is JobApplicationStatus.ADDED
