"""End-to-end audit tests against real Postgres: the seam, the transaction
contract, monotonic ids, and the newest-first reads.

Exercises the whole write path with real collaborators: the composed
:class:`WriteEventPublisher` (audit as its transactional consumer), the SQLAlchemy
repository, and the ``transaction`` boundary. This is where the seam's failure
contract is proven for real: a failing audit append rolls the content write back,
while a failing best-effort side channel leaves the committed write and its audit
row intact.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from floresu.accounts.models import User
from floresu.audit.repository import SqlAlchemyAuditRepository
from floresu.audit.service import AuditService
from floresu.audit.wiring import build_write_event_publisher
from floresu.core.actor import Actor, ActorType
from floresu.core.db import create_db_engine, create_sessionmaker, fetch_optional, transaction
from floresu.core.events import Action, WriteEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]
MISSING_USER_ID = 10_000_000


@pytest.fixture
def migrated_url(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Point settings at the container and bring it to head (idempotent per test)."""
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")
    return postgres_url


async def _insert_user(sessionmaker: async_sessionmaker[AsyncSession], email: str) -> int:
    """Insert a committed user (a content-write prerequisite) and return its id."""
    async with sessionmaker() as session, transaction(session):
        user = User(email=email, password_hash="x")
        session.add(user)
        await session.flush()
        return user.id


async def _user_exists(session: AsyncSession, email: str) -> bool:
    found = await fetch_optional(session, select(User.id).where(User.email == email))
    return found is not None


async def test_publish_appends_one_row_per_write_with_resolved_actor_and_monotonic_id(
    migrated_url: str,
) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    publisher = build_write_event_publisher()
    try:
        user_id = await _insert_user(sessionmaker, "audit-append@example.com")

        # Two writes (human then agent), each published inside its own transaction.
        async with sessionmaker() as session, transaction(session):
            await publisher.publish(
                session,
                WriteEvent(
                    user_id=user_id,
                    actor=Actor(type=ActorType.HUMAN),
                    entity_type="worklog",
                    entity_id=1,
                    action=Action.CREATE,
                ),
            )
        async with sessionmaker() as session, transaction(session):
            await publisher.publish(
                session,
                WriteEvent(
                    user_id=user_id,
                    actor=Actor(type=ActorType.AGENT, label="claude"),
                    entity_type="worklog",
                    entity_id=1,
                    action=Action.UPDATE,
                    summary="Refined the entry",
                ),
            )

        async with sessionmaker() as session:
            feed = await AuditService(SqlAlchemyAuditRepository(session)).activity_feed(
                str(user_id)
            )
    finally:
        await engine.dispose()

    # Exactly one row per write, newest-first, with a strictly increasing id.
    assert [entry.action for entry in feed] == ["update", "create"]
    assert feed[0].id > feed[1].id
    assert feed[0].actor_type == ActorType.AGENT
    assert feed[0].actor_label == "claude"
    assert feed[1].actor_type == ActorType.HUMAN
    assert feed[1].actor_label is None


async def test_a_failing_audit_append_rolls_back_the_content_write(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    publisher = build_write_event_publisher()
    try:
        # The content write (a new user) and a doomed audit append share one
        # transaction; the audit row's FK to a missing user fails on flush.
        with pytest.raises(IntegrityError):
            async with sessionmaker() as session, transaction(session):
                session.add(User(email="rolled-back@example.com", password_hash="x"))
                await publisher.publish(
                    session,
                    WriteEvent(
                        user_id=MISSING_USER_ID,
                        actor=Actor(type=ActorType.HUMAN),
                        entity_type="worklog",
                        entity_id=1,
                        action=Action.CREATE,
                    ),
                )

        # The content write rolled back with the failed audit append.
        async with sessionmaker() as session:
            survivor = await AuditService(SqlAlchemyAuditRepository(session)).activity_feed(
                str(MISSING_USER_ID)
            )
            user_present = await _user_exists(session, "rolled-back@example.com")
    finally:
        await engine.dispose()

    assert survivor == []
    assert user_present is False


async def test_a_failing_best_effort_side_channel_leaves_the_write_committed(
    migrated_url: str,
) -> None:
    async def failing_side_channel(_event: WriteEvent) -> None:
        raise RuntimeError("sse publish is down")

    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    publisher = build_write_event_publisher(best_effort=[failing_side_channel])
    try:
        user_id = await _insert_user(sessionmaker, "best-effort@example.com")

        # publish must not raise despite the down side channel; the write commits.
        async with sessionmaker() as session, transaction(session):
            await publisher.publish(
                session,
                WriteEvent(
                    user_id=user_id,
                    actor=Actor(type=ActorType.HUMAN),
                    entity_type="bullet",
                    entity_id=2,
                    action=Action.CREATE,
                ),
            )

        async with sessionmaker() as session:
            feed = await AuditService(SqlAlchemyAuditRepository(session)).activity_feed(
                str(user_id)
            )
    finally:
        await engine.dispose()

    assert len(feed) == 1
    assert feed[0].entity_type == "bullet"


async def test_item_history_filters_to_one_item_newest_first(migrated_url: str) -> None:
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    publisher = build_write_event_publisher()
    try:
        user_id = await _insert_user(sessionmaker, "item-history@example.com")

        async with sessionmaker() as session, transaction(session):
            for entity_type, entity_id, action in (
                ("resume", 7, Action.CREATE),
                ("worklog", 9, Action.CREATE),
                ("resume", 7, Action.RENDER),
            ):
                await publisher.publish(
                    session,
                    WriteEvent(
                        user_id=user_id,
                        actor=Actor(type=ActorType.HUMAN),
                        entity_type=entity_type,
                        entity_id=entity_id,
                        action=action,
                    ),
                )

        async with sessionmaker() as session:
            history = await AuditService(SqlAlchemyAuditRepository(session)).item_history(
                str(user_id), "resume", 7
            )
    finally:
        await engine.dispose()

    assert [entry.action for entry in history] == ["render", "create"]
    assert all(entry.entity_type == "resume" and entry.entity_id == 7 for entry in history)
