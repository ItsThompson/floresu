"""End-to-end worklog tests against real Postgres: edges, tags, and the audit seam.

Runs the real :class:`WorklogService` over the SQLAlchemy repository and the
composed write-event publisher (audit as its transactional consumer), so a create
proves it writes one ``worklog_entries`` row, its edge rows, and one ``audit_log``
row in a single transaction. Tag reuse, the edge-only tag removal, source
attachment ownership, archive, and the content-hash re-embed gate (the metadata
the audit row carries) are all exercised through the service against real SQL.
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
from floresu.core.errors import Validation
from floresu.core.events import REEMBED_CONTENT_HASH_KEY
from floresu.profile.repository import SqlAlchemySourceRepository
from floresu.profile.service import SourceService
from floresu.worklog.hashing import compute_content_hash
from floresu.worklog.models import Tag, WorklogEntry
from floresu.worklog.repository import SqlAlchemyWorklogRepository
from floresu.worklog.service import WorklogService
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


def _worklog(session: AsyncSession) -> WorklogService:
    return WorklogService(
        session, SqlAlchemyWorklogRepository(session), build_write_event_publisher()
    )


async def _create_source(sessionmaker: async_sessionmaker[AsyncSession], user_id: int) -> int:
    async with sessionmaker() as session:
        service = SourceService(
            session, SqlAlchemySourceRepository(session), build_write_event_publisher()
        )
        record = await service.create(str(user_id), _HUMAN, build_role_write())
        return record.id


async def test_create_writes_entry_edges_and_audit_in_one_transaction(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "wl-create@example.com")
        source_id = await _create_source(sessionmaker, user_id)
        async with sessionmaker() as session:
            record = await _worklog(session).create(
                str(user_id),
                _HUMAN,
                build_worklog_write(tags=["api", "python"], source_ids=[source_id]),
            )

        async with sessionmaker() as session:
            entries = await session.scalar(
                select(func.count())
                .select_from(WorklogEntry)
                .where(WorklogEntry.user_id == user_id)
            )
            tags = await session.scalar(
                select(func.count()).select_from(Tag).where(Tag.user_id == user_id)
            )
            audit = (
                (
                    await session.execute(
                        select(AuditLog).where(
                            AuditLog.entity_type == "worklog", AuditLog.user_id == user_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            entry = await session.get(WorklogEntry, record.id)
            # Re-read through the service so the tag/source edges resolve from SQL.
            reread = await _worklog(session).get(str(user_id), record.id)
    finally:
        await engine.dispose()

    assert entries == 1
    assert tags == 2
    assert record.tags == ["api", "python"]
    assert record.source_ids == [source_id]
    assert len(audit) == 1
    assert audit[0].action == "create"
    assert audit[0].actor_type is ActorType.HUMAN
    # The create carries the re-embed trigger and persists the content hash.
    assert audit[0].event_metadata == {
        REEMBED_CONTENT_HASH_KEY: compute_content_hash(
            "Shipped the search API", "Wired hybrid search behind the internal boundary."
        )
    }
    assert entry is not None
    assert entry.content_hash
    # The edges resolve from SQL on a fresh read, not just from the write's own data.
    assert reread.tags == ["api", "python"]
    assert reread.source_ids == [source_id]


async def test_a_label_is_reused_across_entries(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "wl-tagreuse@example.com")
        async with sessionmaker() as session:
            await _worklog(session).create(str(user_id), _HUMAN, build_worklog_write(tags=["api"]))
        async with sessionmaker() as session:
            await _worklog(session).create(
                str(user_id), _HUMAN, build_worklog_write(tags=["api", "ml"])
            )
        async with sessionmaker() as session:
            tag_count = await session.scalar(
                select(func.count()).select_from(Tag).where(Tag.user_id == user_id)
            )
    finally:
        await engine.dispose()

    # "api" resolves to the existing row, so two distinct labels, not three.
    assert tag_count == 2


async def test_removing_a_tag_from_one_entry_leaves_it_when_another_uses_it(
    migrated_url: str,
) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "wl-tagkeep@example.com")
        async with sessionmaker() as session:
            first = await _worklog(session).create(
                str(user_id), _HUMAN, build_worklog_write(tags=["api", "python"])
            )
        async with sessionmaker() as session:
            await _worklog(session).create(str(user_id), _HUMAN, build_worklog_write(tags=["api"]))
        # Drop "api" from the first entry.
        async with sessionmaker() as session:
            await _worklog(session).update(
                str(user_id), first.id, _HUMAN, build_worklog_write(tags=["python"])
            )
        async with sessionmaker() as session:
            labels = [tag.label for tag in await _worklog(session).list_tags(str(user_id))]
            first_record = await _worklog(session).get(str(user_id), first.id)
    finally:
        await engine.dispose()

    assert "api" in labels  # the tag row survives; the second entry still uses it
    assert first_record.tags == ["python"]


async def test_attaching_a_foreign_source_is_rejected(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        owner = await _insert_user(sessionmaker, "wl-owner@example.com")
        other = await _insert_user(sessionmaker, "wl-other@example.com")
        foreign_source = await _create_source(sessionmaker, other)
        with pytest.raises(Validation):
            async with sessionmaker() as session:
                await _worklog(session).create(
                    str(owner), _HUMAN, build_worklog_write(source_ids=[foreign_source])
                )
    finally:
        await engine.dispose()


async def test_archive_drops_from_the_active_list_and_audits(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "wl-archive@example.com")
        async with sessionmaker() as session:
            created = await _worklog(session).create(str(user_id), _HUMAN, build_worklog_write())
        async with sessionmaker() as session:
            await _worklog(session).archive(str(user_id), created.id, _HUMAN)
        async with sessionmaker() as session:
            active = await _worklog(session).list_entries(str(user_id))
            including = await _worklog(session).list_entries(str(user_id), include_archived=True)
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
    assert [entry.id for entry in including] == [created.id]
    assert set(actions) == {"create", "archive"}


async def test_reembed_trigger_only_fires_when_content_changes(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "wl-reembed@example.com")
        async with sessionmaker() as session:
            created = await _worklog(session).create(str(user_id), _HUMAN, build_worklog_write())
        # A tags-only edit leaves the content hash: no re-embed trigger.
        async with sessionmaker() as session:
            await _worklog(session).update(
                str(user_id), created.id, _HUMAN, build_worklog_write(tags=["api"])
            )
        # A description edit changes the hash: the trigger fires.
        async with sessionmaker() as session:
            await _worklog(session).update(
                str(user_id), created.id, _HUMAN, build_worklog_write(description="Now different.")
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

    # First update (tags only) carries no trigger; second (content) carries the hash.
    assert updates[0] is None
    assert updates[1] == {
        REEMBED_CONTENT_HASH_KEY: compute_content_hash("Shipped the search API", "Now different.")
    }
