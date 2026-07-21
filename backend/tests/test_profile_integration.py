"""End-to-end sources tests against real Postgres: the CTI constraints and the
audit seam.

Runs the real :class:`SourceService` over the SQLAlchemy repository and the
composed write-event publisher (audit as its transactional consumer), so a create
proves it writes one ``sources`` row, one subtype row, and one ``audit_log`` row
in a single transaction. Two negative inserts prove the kind lock: a subtype row
whose ``kind`` disagrees with its base row is rejected by the CHECK plus the
composite FK. Archive and reorder are exercised through the service and read back.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from floresu.accounts.models import User
from floresu.audit.models import AuditLog
from floresu.audit.wiring import build_write_event_publisher
from floresu.core.actor import Actor, ActorType
from floresu.core.db import create_db_engine, create_sessionmaker, transaction
from floresu.core.errors import NotFound
from floresu.profile.models import Role, Source, SourceKind
from floresu.profile.repository import SqlAlchemySourceRepository
from floresu.profile.schemas import ReorderRequest
from floresu.profile.service import SourceService
from tests.profile_fakes import build_role_write

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]
_HUMAN = Actor(type=ActorType.HUMAN)


@pytest.fixture
def migrated_url(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Point settings at the container and bring it to head (idempotent per test)."""
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


def _service(session: AsyncSession) -> SourceService:
    return SourceService(
        session, SqlAlchemySourceRepository(session), build_write_event_publisher()
    )


async def test_create_writes_base_subtype_and_audit_in_one_transaction(
    migrated_url: str,
) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "sources-create@example.com")
        async with sessionmaker() as session:
            record = await _service(session).create(str(user_id), _HUMAN, build_role_write())

        async with sessionmaker() as session:
            sources = await session.scalar(
                select(func.count()).select_from(Source).where(Source.user_id == user_id)
            )
            roles = await session.scalar(
                select(func.count())
                .select_from(Role)
                .join(Source, Source.id == Role.source_id)
                .where(Source.user_id == user_id)
            )
            audit = (
                (
                    await session.execute(
                        select(AuditLog).where(
                            AuditLog.entity_type == "source", AuditLog.user_id == user_id
                        )
                    )
                )
                .scalars()
                .all()
            )
    finally:
        await engine.dispose()

    # One base row, one subtype row, and one audit row for this user's create
    # (counts are scoped to the user because integration tests share one database).
    assert sources == 1
    assert roles == 1
    assert len(audit) == 1
    assert audit[0].action == "create"
    assert audit[0].entity_id == record.id
    assert audit[0].actor_type is ActorType.HUMAN
    # The ``sort_order`` server default is read back on the returned record (the
    # Identity PK forces INSERT...RETURNING and eager_defaults folds it in).
    assert record.sort_order == 0


async def test_create_reads_back_the_server_default_sort_order(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "sources-defaults@example.com")
        # Two creates in the same section both return sort_order 0 (no max+1 probe);
        # this locks in the async server-default read-back for the domain template.
        async with sessionmaker() as session:
            first = await _service(session).create(str(user_id), _HUMAN, build_role_write())
        async with sessionmaker() as session:
            second = await _service(session).create(str(user_id), _HUMAN, build_role_write())
    finally:
        await engine.dispose()

    assert first.sort_order == 0
    assert second.sort_order == 0


async def test_get_of_a_missing_source_is_not_found(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "sources-missing@example.com")
        # Exercises the real SQLAlchemy get_detail "no such row" branch end to end.
        with pytest.raises(NotFound):
            async with sessionmaker() as session:
                await _service(session).get(str(user_id), 9_999_999)
    finally:
        await engine.dispose()


async def test_a_subtype_row_cannot_disagree_with_its_base_kind(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "sources-kindlock@example.com")
        async with sessionmaker() as session:
            role = await _service(session).create(str(user_id), _HUMAN, build_role_write())

        # A subtype row whose kind disagrees with the base row is impossible: the
        # roles CHECK pins kind='role' and the composite FK to sources(id, kind)
        # has no matching (id, 'project') row.
        with pytest.raises(IntegrityError):
            async with sessionmaker() as session, transaction(session):
                await session.execute(
                    text(
                        "INSERT INTO roles (source_id, kind, company, job_title) "
                        "VALUES (:sid, 'project', 'x', 'y')"
                    ),
                    {"sid": role.id},
                )
    finally:
        await engine.dispose()


async def test_a_subtype_cannot_attach_to_a_base_of_another_kind(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "sources-fk@example.com")
        async with sessionmaker() as session:
            role = await _service(session).create(str(user_id), _HUMAN, build_role_write())

        # Attaching a project subtype to a role's base row fails the composite FK.
        with pytest.raises(IntegrityError):
            async with sessionmaker() as session, transaction(session):
                await session.execute(
                    text("INSERT INTO projects (source_id, kind) VALUES (:sid, 'project')"),
                    {"sid": role.id},
                )
    finally:
        await engine.dispose()


async def test_archive_drops_from_the_active_list_and_audits(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "sources-archive@example.com")
        async with sessionmaker() as session:
            created = await _service(session).create(str(user_id), _HUMAN, build_role_write())
        async with sessionmaker() as session:
            await _service(session).archive(str(user_id), created.id, _HUMAN)

        async with sessionmaker() as session:
            active = await _service(session).list_sources(str(user_id))
            including = await _service(session).list_sources(str(user_id), include_archived=True)
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
    assert [s.id for s in including] == [created.id]
    assert set(actions) == {"create", "archive"}


async def test_reorder_persists_sort_order(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        user_id = await _insert_user(sessionmaker, "sources-reorder@example.com")
        ids: list[int] = []
        for label in ("A", "B", "C"):
            async with sessionmaker() as session:
                record = await _service(session).create(
                    str(user_id), _HUMAN, build_role_write(display_label=label)
                )
                ids.append(record.id)

        new_order = [ids[2], ids[0], ids[1]]
        async with sessionmaker() as session:
            await _service(session).reorder(
                str(user_id), _HUMAN, ReorderRequest(kind=SourceKind.ROLE, source_ids=new_order)
            )

        async with sessionmaker() as session:
            listed = await _service(session).list_sources(str(user_id), kind=SourceKind.ROLE)
    finally:
        await engine.dispose()

    assert [s.id for s in listed] == new_order
    assert [s.sort_order for s in listed] == [0, 1, 2]
