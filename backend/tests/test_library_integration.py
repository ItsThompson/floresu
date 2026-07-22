"""End-to-end library tests against real Postgres: edges, the audit seam, the DAG.

Runs the real :class:`LibraryService` over the SQLAlchemy repository and the
composed write-event publisher (audit as its transactional consumer), so a create
proves it writes one ``bulletpoints`` row, its edge rows, and one ``audit_log`` row
in a single transaction. The content-hash re-embed gate, archive, edge-ownership
rejection, and the full three-join provenance DAG (including the ``bullet_worklog``
edges resolving from the worklog side) are all exercised against real SQL.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, select

from floresu.accounts.models import User
from floresu.audit.models import AuditLog
from floresu.audit.wiring import build_write_event_publisher
from floresu.core.actor import Actor, ActorType
from floresu.core.db import create_db_engine, create_sessionmaker, transaction
from floresu.core.errors import Validation
from floresu.core.events import REEMBED_CONTENT_HASH_KEY
from floresu.library.hashing import compute_content_hash
from floresu.library.models import Bulletpoint, BulletSource, BulletWorklog
from floresu.library.provenance import build_provenance_dag
from floresu.library.repository import SqlAlchemyLibraryRepository
from floresu.library.service import LibraryService
from floresu.profile.repository import SqlAlchemySourceRepository
from floresu.profile.service import SourceService
from floresu.resumes.models import Resume, ResumeBulletRef, ResumeKind
from floresu.resumes.repository import SqlAlchemyResumeRepository
from floresu.worklog.models import WorklogSource
from floresu.worklog.repository import SqlAlchemyWorklogRepository
from floresu.worklog.service import WorklogService
from tests.library_fakes import build_bullet_write
from tests.profile_fakes import build_role_write
from tests.worklog_fakes import build_worklog_write

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


def _library(session: AsyncSession) -> LibraryService:
    return LibraryService(
        session,
        SqlAlchemyLibraryRepository(session),
        build_write_event_publisher(),
        SqlAlchemyResumeRepository(session),
    )


async def _create_source(sessionmaker: async_sessionmaker[AsyncSession], user_id: int) -> int:
    async with sessionmaker() as session:
        service = SourceService(
            session, SqlAlchemySourceRepository(session), build_write_event_publisher()
        )
        record = await service.create(str(user_id), _HUMAN, build_role_write())
        return record.id


async def _create_worklog(
    sessionmaker: async_sessionmaker[AsyncSession], user_id: int, *, source_ids: list[int]
) -> int:
    async with sessionmaker() as session:
        service = WorklogService(
            session, SqlAlchemyWorklogRepository(session), build_write_event_publisher()
        )
        record = await service.create(
            str(user_id), _HUMAN, build_worklog_write(source_ids=source_ids)
        )
        return record.id


async def _insert_resume(sessionmaker: async_sessionmaker[AsyncSession], user_id: int) -> int:
    """Insert a bare resume row so a ``resume_bullet_ref`` can satisfy its FK."""
    async with sessionmaker() as session, transaction(session):
        resume = Resume(
            user_id=user_id, kind=ResumeKind.LIVING, title="R", schema_version=1, document={}
        )
        session.add(resume)
        await session.flush()
        return resume.id


async def test_create_writes_bullet_edges_and_audit_in_one_transaction(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "lib-create@example.com")
        source_id = await _create_source(sessionmaker, user_id)
        worklog_id = await _create_worklog(sessionmaker, user_id, source_ids=[source_id])
        async with sessionmaker() as session:
            record = await _library(session).create(
                str(user_id),
                _HUMAN,
                build_bullet_write(source_ids=[source_id], worklog_ids=[worklog_id]),
            )

        async with sessionmaker() as session:
            bullets = await session.scalar(
                select(func.count()).select_from(Bulletpoint).where(Bulletpoint.user_id == user_id)
            )
            source_edges = await session.scalar(
                select(func.count())
                .select_from(BulletSource)
                .where(BulletSource.bullet_id == record.id)
            )
            worklog_edges = await session.scalar(
                select(func.count())
                .select_from(BulletWorklog)
                .where(BulletWorklog.bullet_id == record.id)
            )
            audit = (
                (
                    await session.execute(
                        select(AuditLog).where(
                            AuditLog.entity_type == "bullet", AuditLog.user_id == user_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            bullet = await session.get(Bulletpoint, record.id)
            # Re-read through the service so the edges resolve from SQL.
            reread = await _library(session).get(str(user_id), record.id)
    finally:
        await engine.dispose()

    assert bullets == 1
    assert source_edges == 1
    assert worklog_edges == 1
    assert record.source_ids == [source_id]
    assert record.worklog_ids == [worklog_id]
    assert record.revision == 1
    assert len(audit) == 1
    assert audit[0].action == "create"
    assert audit[0].actor_type is ActorType.HUMAN
    # The create carries the re-embed trigger and persists the content hash.
    assert audit[0].event_metadata == {REEMBED_CONTENT_HASH_KEY: compute_content_hash(record.text)}
    assert bullet is not None
    assert bullet.content_hash
    assert reread.source_ids == [source_id]
    assert reread.worklog_ids == [worklog_id]


async def test_the_three_join_provenance_dag_is_usable_end_to_end(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "lib-dag@example.com")
        source_id = await _create_source(sessionmaker, user_id)
        # The worklog entry rolls up to the source (worklog_source, from T7).
        worklog_id = await _create_worklog(sessionmaker, user_id, source_ids=[source_id])
        # The bullet frames both the worklog entry and the source directly.
        async with sessionmaker() as session:
            bullet = await _library(session).create(
                str(user_id),
                _HUMAN,
                build_bullet_write(source_ids=[source_id], worklog_ids=[worklog_id]),
            )

        async with sessionmaker() as session:
            # The worklog side resolves its framing bullet now that the edges exist.
            worklog_bullets = (
                await SqlAlchemyWorklogRepository(session).bullet_ids_by_worklog([worklog_id])
            ).get(worklog_id, [])
            # The empty-input guard short-circuits without a query.
            empty_guard = await SqlAlchemyWorklogRepository(session).bullet_ids_by_worklog([])
            # Load the three joins' raw edges and assemble the DAG for this hit set.
            bullet_worklog_edges = (
                await session.execute(select(BulletWorklog.bullet_id, BulletWorklog.worklog_id))
            ).all()
            bullet_source_edges = (
                await session.execute(select(BulletSource.bullet_id, BulletSource.source_id))
            ).all()
            worklog_source_edges = (
                await session.execute(select(WorklogSource.worklog_id, WorklogSource.source_id))
            ).all()
    finally:
        await engine.dispose()

    assert worklog_bullets == [bullet.id]
    assert empty_guard == {}
    dag = build_provenance_dag(
        bullet_ids=[bullet.id],
        worklog_ids=[worklog_id],
        source_ids=[source_id],
        bullet_worklog_edges=[(b, w) for b, w in bullet_worklog_edges],
        bullet_source_edges=[(b, s) for b, s in bullet_source_edges],
        worklog_source_edges=[(w, s) for w, s in worklog_source_edges],
    )
    # All three joins present: bullet→worklog, bullet→source, worklog→source.
    assert dag.bullet_worklog == {bullet.id: [worklog_id]}
    assert dag.bullet_source == {bullet.id: [source_id]}
    assert dag.worklog_source == {worklog_id: [source_id]}


async def test_reembed_trigger_only_fires_when_text_changes(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "lib-reembed@example.com")
        source_id = await _create_source(sessionmaker, user_id)
        async with sessionmaker() as session:
            created = await _library(session).create(str(user_id), _HUMAN, build_bullet_write())
        # An edges-only edit leaves the content hash: no re-embed trigger.
        async with sessionmaker() as session:
            await _library(session).update(
                str(user_id), created.id, _HUMAN, build_bullet_write(source_ids=[source_id])
            )
        # A text edit changes the hash: the trigger fires.
        async with sessionmaker() as session:
            await _library(session).update(
                str(user_id), created.id, _HUMAN, build_bullet_write(text="A new framing entirely.")
            )
        async with sessionmaker() as session:
            updates = (
                (
                    await session.execute(
                        select(AuditLog.event_metadata)
                        .where(AuditLog.entity_id == created.id, AuditLog.action == "update")
                        .order_by(AuditLog.id)
                    )
                )
                .scalars()
                .all()
            )
    finally:
        await engine.dispose()

    assert updates[0] is None
    assert updates[1] == {REEMBED_CONTENT_HASH_KEY: compute_content_hash("A new framing entirely.")}


async def test_archive_drops_from_library_reads_and_from_worklog_framing(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "lib-archive@example.com")
        worklog_id = await _create_worklog(sessionmaker, user_id, source_ids=[])
        async with sessionmaker() as session:
            created = await _library(session).create(
                str(user_id), _HUMAN, build_bullet_write(worklog_ids=[worklog_id])
            )
        async with sessionmaker() as session:
            await _library(session).archive(str(user_id), created.id, _HUMAN)
        async with sessionmaker() as session:
            active = await _library(session).list_bullets(str(user_id))
            including = await _library(session).list_bullets(str(user_id), include_archived=True)
            # An archived bullet leaves the worklog entry's framing list too.
            worklog_bullets = (
                await SqlAlchemyWorklogRepository(session).bullet_ids_by_worklog([worklog_id])
            ).get(worklog_id, [])
            actions = (
                (
                    await session.execute(
                        select(AuditLog.action).where(AuditLog.entity_id == created.id)
                    )
                )
                .scalars()
                .all()
            )
    finally:
        await engine.dispose()

    assert active == []
    assert [bullet.id for bullet in including] == [created.id]
    assert worklog_bullets == []
    assert set(actions) == {"create", "archive"}


async def test_framing_a_foreign_source_or_worklog_is_rejected(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        owner = await _insert_user(sessionmaker, "lib-owner@example.com")
        other = await _insert_user(sessionmaker, "lib-other@example.com")
        foreign_source = await _create_source(sessionmaker, other)
        foreign_worklog = await _create_worklog(sessionmaker, other, source_ids=[foreign_source])
        with pytest.raises(Validation):
            async with sessionmaker() as session:
                await _library(session).create(
                    str(owner), _HUMAN, build_bullet_write(source_ids=[foreign_source])
                )
        with pytest.raises(Validation):
            async with sessionmaker() as session:
                await _library(session).create(
                    str(owner), _HUMAN, build_bullet_write(worklog_ids=[foreign_worklog])
                )
    finally:
        await engine.dispose()


async def test_list_reports_real_used_in_count_over_refs(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "lib-usage@example.com")
        async with sessionmaker() as session:
            shared = await _library(session).create(
                str(user_id), _HUMAN, build_bullet_write(text="Shared bullet.")
            )
            once = await _library(session).create(
                str(user_id), _HUMAN, build_bullet_write(text="Used once.")
            )
            unused = await _library(session).create(
                str(user_id), _HUMAN, build_bullet_write(text="Unused bullet.")
            )
        resume_a = await _insert_resume(sessionmaker, user_id)
        resume_b = await _insert_resume(sessionmaker, user_id)
        # Two resumes reference `shared`, one references `once`, none reference `unused`.
        async with sessionmaker() as session, transaction(session):
            session.add_all(
                [
                    ResumeBulletRef(resume_id=resume_a, bullet_id=shared.id),
                    ResumeBulletRef(resume_id=resume_b, bullet_id=shared.id),
                    ResumeBulletRef(resume_id=resume_a, bullet_id=once.id),
                ]
            )
        async with sessionmaker() as session:
            listed = await _library(session).list_bullets(str(user_id))
            fetched = await _library(session).get(str(user_id), shared.id)
    finally:
        await engine.dispose()

    by_id = {record.id: record.used_in_count for record in listed}
    assert by_id == {shared.id: 2, once.id: 1, unused.id: 0}
    # The list count equals the single-read count for the same bullet.
    assert fetched.used_in_count == 2


async def test_dropping_refs_lowers_the_library_count(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "lib-usage-drop@example.com")
        async with sessionmaker() as session:
            bullet = await _library(session).create(
                str(user_id), _HUMAN, build_bullet_write(text="Referenced then dropped.")
            )
        resume_a = await _insert_resume(sessionmaker, user_id)
        resume_b = await _insert_resume(sessionmaker, user_id)
        async with sessionmaker() as session, transaction(session):
            session.add_all(
                [
                    ResumeBulletRef(resume_id=resume_a, bullet_id=bullet.id),
                    ResumeBulletRef(resume_id=resume_b, bullet_id=bullet.id),
                ]
            )
        async with sessionmaker() as session:
            before = (await _library(session).get(str(user_id), bullet.id)).used_in_count
        # Finalize drops a resume's refs; simulate by removing one resume's rows.
        async with sessionmaker() as session, transaction(session):
            await session.execute(
                delete(ResumeBulletRef).where(ResumeBulletRef.resume_id == resume_b)
            )
        async with sessionmaker() as session:
            after = (await _library(session).get(str(user_id), bullet.id)).used_in_count
    finally:
        await engine.dispose()

    assert before == 2
    assert after == 1
