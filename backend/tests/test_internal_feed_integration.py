"""The composed internal (agent) app streams a committed write to the live feed.

Runtime proof over the real :func:`create_internal_app` composition rather than a
hand-wired publisher. The internal app is what the MCP server proxies agent writes
to; it registers the SSE feed consumer, so an agent write fans out to the owner's
Redis feed channel + replay buffer that the external app's ``GET /feed`` streams
from. A committed agent write must arrive on the channel carrying the monotonic
audit id and the agent actor; a rolled-back write must publish nothing (post-commit
only). Skips when Docker is unavailable.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from alembic import command
from alembic.config import Config

from floresu.accounts.models import User
from floresu.api_internal.main import create_internal_app
from floresu.core.actor import Actor, ActorType
from floresu.core.db import Database, transaction
from floresu.core.events import Action, WriteEvent, get_events
from floresu.core.redis import create_redis_client
from floresu.feed.store import RedisFeedStore

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


def _agent_write(user_id: int, *, entity_id: int) -> WriteEvent:
    return WriteEvent(
        user_id=user_id,
        actor=Actor(type=ActorType.AGENT, label="claude"),
        entity_type="worklog",
        entity_id=entity_id,
        action=Action.CREATE,
    )


async def test_the_internal_app_streams_an_agent_write_to_the_live_feed(
    migrated_url: str, redis_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REDIS_URL", redis_url)
    app = create_internal_app()
    sessionmaker = cast("Database", app.state.db).sessionmaker
    publisher = get_events(app)

    # A separate client on the same Redis stands in for the external app's GET /feed:
    # it subscribes to the owner's channel the internal app publishes to.
    observer_redis = create_redis_client(redis_url)
    observer = RedisFeedStore(observer_redis)
    try:
        await observer_redis.flushdb()
        async with app.router.lifespan_context(app):
            user_id = await _insert_user(sessionmaker, "agent-feed-live@example.com")

            # Subscribe first; the initial idle tick confirms the subscription is live.
            stream = observer.listen(user_id, heartbeat_timeout=0.2)
            assert await stream.__anext__() is None

            async with sessionmaker() as session, transaction(session):
                await publisher.publish(session, _agent_write(user_id, entity_id=5))

            # The committed agent write fanned out to the feed channel, attributed to
            # the agent and carrying the durable audit id.
            live = await asyncio.wait_for(stream.__anext__(), timeout=2)
            assert live is not None
            assert live.actor_type == ActorType.AGENT
            assert live.actor_label == "claude"
            assert live.entity_type == "worklog"
            assert live.entity_id == 5
            assert live.id > 0

            # And it entered the bounded replay buffer, so a reconnecting client with
            # a prior Last-Event-ID replays it.
            gap = await observer.replay_since(user_id, last_event_id=0)
            assert [entry.id for entry in gap] == [live.id]
            await stream.aclose()
    finally:
        await observer_redis.aclose()


async def test_the_internal_app_publishes_nothing_for_a_rolled_back_agent_write(
    migrated_url: str, redis_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REDIS_URL", redis_url)
    app = create_internal_app()
    sessionmaker = cast("Database", app.state.db).sessionmaker
    publisher = get_events(app)

    observer_redis = create_redis_client(redis_url)
    observer = RedisFeedStore(observer_redis)
    try:
        await observer_redis.flushdb()
        async with app.router.lifespan_context(app):
            user_id = await _insert_user(sessionmaker, "agent-feed-rollback@example.com")

            with pytest.raises(RuntimeError, match="boom"):
                async with sessionmaker() as session, transaction(session):
                    await publisher.publish(session, _agent_write(user_id, entity_id=6))
                    raise RuntimeError("boom")

            # The post-commit SSE publish is deferred and discarded on rollback, so
            # nothing reached the channel or the replay buffer.
            gap = await observer.replay_since(user_id, last_event_id=0)
            assert gap == []
    finally:
        await observer_redis.aclose()
