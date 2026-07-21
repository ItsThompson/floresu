"""Integration test: a real arq enqueue -> dequeue round trip over real Redis.

Proves the queue-name and job-name contract end to end: a job enqueued on
``EMBED_QUEUE_NAME`` with the ``embed_item`` name and positional args is routed by
arq to the worker's :func:`embed_item`, which reads the item and writes the vector
back through the (fake) internal client. Skips without Docker, mirroring the
backend/mcp testcontainers usage.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from arq.connections import ArqRedis, RedisSettings
from arq.worker import Worker

from floresu_worker.config import EMBED_ITEM_JOB, EMBED_QUEUE_NAME, PURGE_ITEM_JOB
from floresu_worker.embed_tasks import embed_item, purge_item
from floresu_worker.schemas import EmbedItemContent
from tests.fakes import FakeInternalClient, FakeProvider

pytestmark = pytest.mark.integration

REDIS_IMAGE = "redis:7-alpine"


@pytest.fixture(scope="module")
def redis_dsn() -> Iterator[str]:
    try:
        from testcontainers.redis import RedisContainer
    except ImportError:  # pragma: no cover - env without testcontainers
        pytest.skip("testcontainers not installed")
    try:
        with RedisContainer(REDIS_IMAGE) as container:
            host = container.get_container_host_ip()
            port = container.get_exposed_port(6379)
            yield f"redis://{host}:{port}/0"
    except Exception as exc:  # pragma: no cover - Docker daemon unavailable
        pytest.skip(f"Docker unavailable for integration tests: {exc}")


def _worker(redis_dsn: str, client: FakeInternalClient) -> Worker:
    async def on_startup(ctx: dict[str, object]) -> None:
        ctx["client"] = client
        ctx["provider"] = FakeProvider()

    return Worker(
        functions=[embed_item, purge_item],
        queue_name=EMBED_QUEUE_NAME,
        redis_settings=RedisSettings.from_dsn(redis_dsn),
        on_startup=on_startup,
        burst=True,
        handle_signals=False,
    )


async def test_enqueued_embed_job_is_routed_to_the_task(redis_dsn: str) -> None:
    pool = ArqRedis.from_url(redis_dsn)
    await pool.enqueue_job(EMBED_ITEM_JOB, 1, "worklog", 5, "h1", _queue_name=EMBED_QUEUE_NAME)
    client = FakeInternalClient(
        item=EmbedItemContent(text="shipped it", content_hash="h1", archived=False)
    )

    worker = _worker(redis_dsn, client)
    await worker.async_run()
    await worker.close()

    # arq routed the job to embed_item with the deserialized args, which read the
    # item and wrote the vector back.
    assert client.gets == [(1, "worklog", 5)]
    assert len(client.puts) == 1
    await pool.aclose()


async def test_enqueued_purge_job_is_routed_to_the_task(redis_dsn: str) -> None:
    pool = ArqRedis.from_url(redis_dsn)
    await pool.enqueue_job(PURGE_ITEM_JOB, 1, "source", 7, _queue_name=EMBED_QUEUE_NAME)
    client = FakeInternalClient()

    worker = _worker(redis_dsn, client)
    await worker.async_run()
    await worker.close()

    assert client.deletes == [(1, "source", 7)]
    await pool.aclose()
