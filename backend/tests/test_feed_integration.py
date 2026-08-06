"""End-to-end feed test: a committed write reaches the live feed, a rollback does not.

The definitive runtime proof of the write-event seam, wired exactly as the external
app composes it: the real :class:`WriteEventPublisher` with the audit transactional
consumer and the SSE feed publish as a post-commit consumer, over real Postgres
(the audit append + commit) and real Redis (the pub/sub fan-out). A committed write
must arrive on the user's feed channel carrying the monotonic audit id; a
rolled-back write must never emit. Skips when Docker is unavailable.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config

from floresu.accounts.models import User
from floresu.audit.wiring import build_write_event_publisher
from floresu.core.actor import Actor, ActorType
from floresu.core.db import create_db_engine, create_sessionmaker, transaction
from floresu.core.events import Action, WriteEvent
from floresu.core.redis import create_redis_client
from floresu.feed.store import RedisFeedStore
from floresu.feed.wiring import build_sse_feed_consumer

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]


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


async def test_a_committed_write_reaches_the_live_feed_channel(
    migrated_url: str, redis_url: str
) -> None:
    redis = create_redis_client(redis_url)
    store = RedisFeedStore(redis)
    # Composed exactly as api/main.py wires it: audit transactional + SSE post-commit.
    publisher = build_write_event_publisher(post_commit=[build_sse_feed_consumer(store)])
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        await redis.flushdb()
        user_id = await _insert_user(sessionmaker, "feed-e2e@example.com")

        # Subscribe first; the initial idle tick confirms the subscription is live.
        stream = store.listen(user_id, heartbeat_timeout=0.2)
        assert await stream.__anext__() is None

        async with sessionmaker() as session, transaction(session):
            await publisher.publish(
                session,
                WriteEvent(
                    user_id=user_id,
                    actor=Actor(type=ActorType.HUMAN),
                    entity_type="worklog",
                    entity_id=5,
                    action=Action.CREATE,
                ),
            )

        # The committed write fanned out to the feed channel with the audit id.
        live = await asyncio.wait_for(stream.__anext__(), timeout=2)
        assert live is not None
        assert live.entity_type == "worklog"
        assert live.entity_id == 5
        assert live.id > 0

        # And it is in the replay buffer for a reconnecting client.
        gap = await store.replay_since(user_id, last_event_id=0)
        assert [entry.id for entry in gap] == [live.id]
        await stream.aclose()
    finally:
        await redis.aclose()
        await engine.dispose()


async def test_a_rolled_back_write_never_reaches_the_feed_channel(
    migrated_url: str, redis_url: str
) -> None:
    redis = create_redis_client(redis_url)
    store = RedisFeedStore(redis)
    publisher = build_write_event_publisher(post_commit=[build_sse_feed_consumer(store)])
    engine = create_db_engine(migrated_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        await redis.flushdb()
        user_id = await _insert_user(sessionmaker, "feed-rollback@example.com")

        with pytest.raises(RuntimeError, match="boom"):
            async with sessionmaker() as session, transaction(session):
                await publisher.publish(
                    session,
                    WriteEvent(
                        user_id=user_id,
                        actor=Actor(type=ActorType.HUMAN),
                        entity_type="worklog",
                        entity_id=6,
                        action=Action.CREATE,
                    ),
                )
                raise RuntimeError("boom")

        # Nothing was published: the replay buffer for the user is empty.
        gap = await store.replay_since(user_id, last_event_id=0)
        assert gap == []
    finally:
        await redis.aclose()
        await engine.dispose()
