"""End-to-end resume tests against real Postgres: the document, index, revisions.

Runs the real :class:`ResumeService` over the SQLAlchemy repository, the real
bullet-text resolver, and the composed write-event publisher (audit as its
transactional consumer), so a save proves it writes the ``resumes`` row, reindexes
``resume_bullet_ref``, appends a fully resolved ``resume_revisions`` snapshot, and
records one ``audit_log`` row in a single transaction. The optimistic-concurrency
guard, the "used in N" count, the snapshot's immunity to a later library edit, the
1:1 job-application link, and seeding from a source are all exercised against real
SQL.
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
from floresu.library.cow import LibraryCanonicalBulletWriter
from floresu.library.repository import SqlAlchemyLibraryRepository
from floresu.library.schemas import BulletpointWrite
from floresu.library.service import LibraryService
from floresu.resumes.document import LocalItem
from floresu.resumes.models import (
    JobApplication,
    Resume,
    ResumeBulletRef,
    ResumeKind,
    ResumeRevision,
)
from floresu.resumes.repository import SqlAlchemyResumeRepository
from floresu.resumes.resolver import SqlAlchemyBulletTextResolver
from floresu.resumes.schemas import ResumeCreateRequest, ResumeUpdate
from floresu.resumes.service import ResumeService

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
        japp = JobApplication(user_id=user_id, company="Acme", role_title="Backend Engineer")
        session.add(japp)
        await session.flush()
        return japp.id


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


def _ref_section(bullet_id: int) -> dict[str, object]:
    return {
        "id": "sec-work",
        "kind": "work",
        "title": "Experience",
        "item_order": ["a"],
        "items": {"a": {"id": "a", "kind": "library_ref", "bullet_id": bullet_id}},
    }


async def test_create_writes_resume_revision_and_audit_in_one_transaction(
    migrated_url: str,
) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "res-create@example.com")
        async with sessionmaker() as session:
            record = await _resumes(session).create(
                str(user_id),
                _HUMAN,
                ResumeCreateRequest.model_validate({"kind": "living", "source": {"mode": "blank"}}),
            )
        async with sessionmaker() as session:
            resumes = await session.scalar(
                select(func.count()).select_from(Resume).where(Resume.user_id == user_id)
            )
            revisions = (
                (
                    await session.execute(
                        select(ResumeRevision).where(ResumeRevision.resume_id == record.id)
                    )
                )
                .scalars()
                .all()
            )
            audit = (
                (
                    await session.execute(
                        select(AuditLog).where(
                            AuditLog.entity_type == "resume", AuditLog.user_id == user_id
                        )
                    )
                )
                .scalars()
                .all()
            )
    finally:
        await engine.dispose()

    assert resumes == 1
    assert record.revision == 1
    assert len(revisions) == 1
    assert revisions[0].revision_no == 1
    assert revisions[0].schema_version == 1
    assert len(audit) == 1
    assert audit[0].action == "create"
    assert audit[0].event_metadata == {"revision": 1}


async def test_reference_indexes_bullet_ref_and_used_in_count(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "res-ref@example.com")
        bullet_id = await _create_bullet(sessionmaker, user_id, "Cut latency 40%.")
        async with sessionmaker() as session:
            created = await _resumes(session).create(
                str(user_id),
                _HUMAN,
                ResumeCreateRequest.model_validate({"kind": "living", "source": {"mode": "blank"}}),
            )
        async with sessionmaker() as session:
            updated = await _resumes(session).update(
                str(user_id),
                created.id,
                _HUMAN,
                created.revision,
                ResumeUpdate.model_validate(
                    {
                        "title": "Living",
                        "template_id": "default",
                        "header": {},
                        "sections": [_ref_section(bullet_id)],
                    }
                ),
            )
        async with sessionmaker() as session:
            refs = (
                (
                    await session.execute(
                        select(ResumeBulletRef.bullet_id).where(
                            ResumeBulletRef.resume_id == created.id
                        )
                    )
                )
                .scalars()
                .all()
            )
            count = await _resumes(session).bullet_used_in_count(str(user_id), bullet_id)
            # The batched grouped count agrees with the singular count for the same
            # bullet, omits an unreferenced id, and returns {} for an empty request.
            repo = SqlAlchemyResumeRepository(session)
            batched = await repo.used_in_counts([bullet_id, bullet_id + 9_999])
            empty_batched = await repo.used_in_counts([])
            snapshot = await session.get(ResumeRevision, (created.id, updated.revision))
    finally:
        await engine.dispose()

    assert list(refs) == [bullet_id]
    assert count == 1
    assert batched == {bullet_id: 1}
    assert empty_batched == {}
    assert snapshot is not None
    # The snapshot resolved the reference to inline text at save time.
    assert snapshot.document["sections"][0]["items"]["a"]["text"] == "Cut latency 40%."
    assert snapshot.document["sections"][0]["items"]["a"]["kind"] == "local"


async def test_revision_snapshot_is_immune_to_a_later_library_edit(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "res-immune@example.com")
        bullet_id = await _create_bullet(sessionmaker, user_id, "Original framing.")
        async with sessionmaker() as session:
            created = await _resumes(session).create(
                str(user_id),
                _HUMAN,
                ResumeCreateRequest.model_validate({"kind": "living", "source": {"mode": "blank"}}),
            )
        async with sessionmaker() as session:
            with_ref = await _resumes(session).update(
                str(user_id),
                created.id,
                _HUMAN,
                created.revision,
                ResumeUpdate.model_validate(
                    {
                        "title": "Living",
                        "template_id": "default",
                        "header": {},
                        "sections": [_ref_section(bullet_id)],
                    }
                ),
            )
        # Edit the canonical bullet, then save the resume again.
        await _edit_bullet(sessionmaker, user_id, bullet_id, "Edited framing.")
        async with sessionmaker() as session:
            await _resumes(session).update(
                str(user_id),
                created.id,
                _HUMAN,
                with_ref.revision,
                ResumeUpdate.model_validate(
                    {
                        "title": "Living",
                        "template_id": "default",
                        "header": {},
                        "sections": [_ref_section(bullet_id)],
                    }
                ),
            )
        async with sessionmaker() as session:
            snapshot_two = await session.get(ResumeRevision, (created.id, 2))
            snapshot_three = await session.get(ResumeRevision, (created.id, 3))
    finally:
        await engine.dispose()

    assert snapshot_two is not None
    assert snapshot_three is not None
    assert snapshot_two.document["sections"][0]["items"]["a"]["text"] == "Original framing."
    assert snapshot_three.document["sections"][0]["items"]["a"]["text"] == "Edited framing."


async def test_stale_if_match_is_rejected(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "res-stale@example.com")
        async with sessionmaker() as session:
            created = await _resumes(session).create(
                str(user_id),
                _HUMAN,
                ResumeCreateRequest.model_validate({"kind": "living", "source": {"mode": "blank"}}),
            )
        async with sessionmaker() as session:
            await _resumes(session).update(
                str(user_id),
                created.id,
                _HUMAN,
                created.revision,
                ResumeUpdate.model_validate(
                    {"title": "First", "template_id": "default", "header": {}, "sections": []}
                ),
            )
        with pytest.raises(Conflict):
            async with sessionmaker() as session:
                await _resumes(session).update(
                    str(user_id),
                    created.id,
                    _HUMAN,
                    1,
                    ResumeUpdate.model_validate(
                        {"title": "Stale", "template_id": "default", "header": {}, "sections": []}
                    ),
                )
        async with sessionmaker() as session:
            reread = await _resumes(session).get(str(user_id), created.id)
    finally:
        await engine.dispose()

    assert reread.title == "First"
    assert reread.revision == 2


async def test_a_concurrent_snapshot_collision_is_a_recoverable_conflict(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "res-race@example.com")
        async with sessionmaker() as session:
            created = await _resumes(session).create(
                str(user_id),
                _HUMAN,
                ResumeCreateRequest.model_validate({"kind": "living", "source": {"mode": "blank"}}),
            )
        # Simulate a genuinely simultaneous writer: it already committed revision 2,
        # so our own write (which also read revision 1 and passed the guard) collides
        # on the resume_revisions primary key.
        async with sessionmaker() as session, transaction(session):
            session.add(
                ResumeRevision(
                    resume_id=created.id,
                    revision_no=2,
                    document={"schema_version": 1, "template_id": "default", "sections": []},
                    schema_version=1,
                )
            )
        with pytest.raises(Conflict):
            async with sessionmaker() as session:
                await _resumes(session).update(
                    str(user_id),
                    created.id,
                    _HUMAN,
                    created.revision,
                    ResumeUpdate.model_validate(
                        {"title": "Racing", "template_id": "default", "header": {}, "sections": []}
                    ),
                )
        async with sessionmaker() as session:
            reread = await _resumes(session).get(str(user_id), created.id)
    finally:
        await engine.dispose()

    # The losing write rolled back cleanly: the row is still at revision 1.
    assert reread.revision == 1
    assert reread.title != "Racing"


async def test_application_resume_links_a_job_application_one_to_one(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "res-app@example.com")
        japp_id = await _insert_job_application(sessionmaker, user_id)
        async with sessionmaker() as session:
            record = await _resumes(session).create(
                str(user_id),
                _HUMAN,
                ResumeCreateRequest.model_validate(
                    {
                        "kind": "application",
                        "source": {"mode": "blank"},
                        "job_application_id": japp_id,
                    }
                ),
            )
        async with sessionmaker() as session:
            stored = await session.get(Resume, record.id)
    finally:
        await engine.dispose()

    assert record.kind.value == "application"
    assert stored is not None
    assert stored.job_application_id == japp_id


async def test_from_resume_copies_the_document_and_records_the_fork(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "res-fork@example.com")
        async with sessionmaker() as session:
            source = await _resumes(session).create(
                str(user_id),
                _HUMAN,
                ResumeCreateRequest.model_validate({"kind": "living", "source": {"mode": "blank"}}),
            )
        local_section = {
            "id": "sec-work",
            "kind": "work",
            "title": "Experience",
            "item_order": ["a"],
            "items": {"a": {"id": "a", "kind": "local", "text": "Net-new item."}},
        }
        async with sessionmaker() as session:
            await _resumes(session).update(
                str(user_id),
                source.id,
                _HUMAN,
                source.revision,
                ResumeUpdate.model_validate(
                    {
                        "title": "Source",
                        "template_id": "default",
                        "header": {},
                        "sections": [local_section],
                    }
                ),
            )
        async with sessionmaker() as session:
            seeded = await _resumes(session).create(
                str(user_id),
                _HUMAN,
                ResumeCreateRequest.model_validate(
                    {
                        "kind": "living",
                        "source": {"mode": "from_resume", "from_resume_id": source.id},
                    }
                ),
            )
    finally:
        await engine.dispose()

    assert seeded.forked_from_resume_id == source.id
    seeded_item = seeded.document.sections[0].items["a"]
    assert isinstance(seeded_item, LocalItem)
    assert seeded_item.text == "Net-new item."


async def test_sql_repository_lists_by_kind_and_short_circuits_empty_inputs(
    migrated_url: str,
) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "res-list@example.com")
        japp_id = await _insert_job_application(sessionmaker, user_id)
        async with sessionmaker() as session:
            resumes = _resumes(session)
            living = await resumes.create(
                str(user_id),
                _HUMAN,
                ResumeCreateRequest.model_validate({"kind": "living", "source": {"mode": "blank"}}),
            )
            await resumes.create(
                str(user_id),
                _HUMAN,
                ResumeCreateRequest.model_validate(
                    {
                        "kind": "application",
                        "source": {"mode": "blank"},
                        "job_application_id": japp_id,
                    }
                ),
            )
        async with sessionmaker() as session:
            repo = SqlAlchemyResumeRepository(session)
            only_living = await repo.list_resumes(
                user_id, kind=ResumeKind.LIVING, include_archived=False, limit=50
            )
            # The empty-input guards short-circuit without a query.
            assert await repo.owned_job_application_ids(user_id, []) == set()
            assert await SqlAlchemyBulletTextResolver(session).resolve(user_id, []) == {}
    finally:
        await engine.dispose()

    assert [row.id for row in only_living] == [living.id]
