"""End-to-end embedding-pipeline tests over real Postgres.

Runs the real :class:`WorklogService` and the composed write-event publisher, so a
content write drives the post-commit embed seam exactly as it does in production,
with only the two true external boundaries faked: OpenAI (a fake provider) and the
arq broker (a recording queue). Covers the async enqueue path (the external/web
app's default), the synchronous fast-path (the internal/agent app), the
content-hash gate on enqueue, and archive-driven vector removal.
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
from floresu.embedding.config import EmbedItemKind
from floresu.embedding.corpus import CorpusResolver
from floresu.embedding.enqueue import (
    build_async_embed_enqueue_consumer,
    build_sync_embed_fastpath_consumer,
)
from floresu.embedding.repository import SqlAlchemyEmbeddingRepository
from floresu.worklog.hashing import compute_content_hash
from floresu.worklog.repository import SqlAlchemyWorklogRepository
from floresu.worklog.service import WorklogService
from tests.embedding_fakes import FakeEmbeddingProvider, FakeEmbedQueue
from tests.worklog_fakes import build_worklog_write

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from floresu.core.events import WriteEventPublisher

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]
_HUMAN = Actor(type=ActorType.HUMAN)


@pytest.fixture
def sessionmaker(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> async_sessionmaker[AsyncSession]:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")
    return create_sessionmaker(create_db_engine(postgres_url))


async def _insert_user(sessionmaker: async_sessionmaker[AsyncSession], email: str) -> int:
    async with sessionmaker() as session, transaction(session):
        user = User(email=email, password_hash="x")
        session.add(user)
        await session.flush()
        return user.id


async def _create_worklog(
    sessionmaker: async_sessionmaker[AsyncSession],
    publisher: WriteEventPublisher,
    user_id: int,
    **write_overrides: object,
) -> int:
    async with sessionmaker() as session:
        service = WorklogService(session, SqlAlchemyWorklogRepository(session), publisher)
        record = await service.create(str(user_id), _HUMAN, build_worklog_write(**write_overrides))
        return record.id


async def _embedding(sessionmaker: async_sessionmaker[AsyncSession], item_id: int) -> object | None:
    async with sessionmaker() as session:
        return await SqlAlchemyEmbeddingRepository(session).get(EmbedItemKind.WORKLOG, item_id)


async def test_async_path_enqueues_one_job_on_create(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    queue = FakeEmbedQueue()
    publisher = build_write_event_publisher(post_commit=[build_async_embed_enqueue_consumer(queue)])
    user_id = await _insert_user(sessionmaker, "embed-async-create@test.dev")

    worklog_id = await _create_worklog(
        sessionmaker, publisher, user_id, title="Shipped the pipeline", description="Details."
    )

    expected_hash = compute_content_hash("Shipped the pipeline", "Details.")
    assert queue.embeds == [(user_id, EmbedItemKind.WORKLOG, worklog_id, expected_hash)]
    assert queue.purges == []


async def test_async_path_enqueues_nothing_on_edges_only_edit(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    queue = FakeEmbedQueue()
    publisher = build_write_event_publisher(post_commit=[build_async_embed_enqueue_consumer(queue)])
    user_id = await _insert_user(sessionmaker, "embed-async-edit@test.dev")
    worklog_id = await _create_worklog(
        sessionmaker, publisher, user_id, title="Title", description="Body"
    )
    queue.embeds.clear()

    # Re-save with identical content (same title/description) -> hash unchanged.
    async with sessionmaker() as session:
        service = WorklogService(session, SqlAlchemyWorklogRepository(session), publisher)
        await service.update(
            str(user_id),
            worklog_id,
            _HUMAN,
            build_worklog_write(title="Title", description="Body"),
        )

    assert queue.embeds == []


async def test_async_path_enqueues_purge_on_archive(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    queue = FakeEmbedQueue()
    publisher = build_write_event_publisher(post_commit=[build_async_embed_enqueue_consumer(queue)])
    user_id = await _insert_user(sessionmaker, "embed-async-archive@test.dev")
    worklog_id = await _create_worklog(sessionmaker, publisher, user_id, title="T", description="D")

    async with sessionmaker() as session:
        service = WorklogService(session, SqlAlchemyWorklogRepository(session), publisher)
        await service.archive(str(user_id), worklog_id, _HUMAN)

    assert queue.purges == [(user_id, EmbedItemKind.WORKLOG, worklog_id)]


async def test_fast_path_embeds_inline_so_a_same_turn_search_would_find_it(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    provider = FakeEmbeddingProvider()
    publisher = build_write_event_publisher(
        post_commit=[build_sync_embed_fastpath_consumer(sessionmaker, CorpusResolver(), provider)]
    )
    user_id = await _insert_user(sessionmaker, "embed-fastpath@test.dev")

    worklog_id = await _create_worklog(
        sessionmaker, publisher, user_id, title="Fast", description="Path"
    )

    stored = await _embedding(sessionmaker, worklog_id)
    assert stored is not None  # the vector is committed before the write returns
    assert provider.calls == [["Fast\n\nPath"]]


async def test_fast_path_removes_the_vector_on_archive(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    provider = FakeEmbeddingProvider()
    publisher = build_write_event_publisher(
        post_commit=[build_sync_embed_fastpath_consumer(sessionmaker, CorpusResolver(), provider)]
    )
    user_id = await _insert_user(sessionmaker, "embed-fastpath-archive@test.dev")
    worklog_id = await _create_worklog(sessionmaker, publisher, user_id, title="T", description="D")
    assert await _embedding(sessionmaker, worklog_id) is not None

    async with sessionmaker() as session:
        service = WorklogService(session, SqlAlchemyWorklogRepository(session), publisher)
        await service.archive(str(user_id), worklog_id, _HUMAN)

    assert await _embedding(sessionmaker, worklog_id) is None


async def test_fast_path_is_idempotent_on_repeated_content_writes(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    provider = FakeEmbeddingProvider()
    publisher = build_write_event_publisher(
        post_commit=[build_sync_embed_fastpath_consumer(sessionmaker, CorpusResolver(), provider)]
    )
    user_id = await _insert_user(sessionmaker, "embed-fastpath-idem@test.dev")
    worklog_id = await _create_worklog(
        sessionmaker, publisher, user_id, title="Same", description="Body"
    )
    assert provider.calls == [["Same\n\nBody"]]

    # Re-save identical content: the hash is unchanged, so the fast-path re-runs but
    # the stored vector already carries the hash -> idempotent, no second embed call.
    async with sessionmaker() as session:
        service = WorklogService(session, SqlAlchemyWorklogRepository(session), publisher)
        await service.update(
            str(user_id), worklog_id, _HUMAN, build_worklog_write(title="Same", description="Body")
        )

    assert provider.calls == [["Same\n\nBody"]]  # no second embed for an unchanged hash
