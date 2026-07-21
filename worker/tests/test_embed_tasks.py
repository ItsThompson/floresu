"""Unit tests for the worker's embed and purge jobs.

The jobs run over fake doubles at every boundary. They cover the gate outcomes the
worker itself decides (missing, archived, superseded), the applied path that embeds
and writes back, the purge path, and the failure path that counts ``failed`` and
re-raises for arq to retry. Each job records its outcome and samples the queue
depth, so the metrics are asserted by their sample deltas.
"""

from __future__ import annotations

from typing import Any

import pytest

from floresu_worker.config import EMBED_QUEUE_NAME
from floresu_worker.embed_tasks import embed_item, purge_item
from floresu_worker.metrics import WORKER_REGISTRY
from floresu_worker.schemas import EmbedItemContent
from tests.fakes import FailingClient, FakeInternalClient, FakeProvider, FakeRedis


def _completed(status: str) -> float:
    value = WORKER_REGISTRY.get_sample_value("embed_jobs_completed_total", {"status": status})
    return value or 0.0


def _ctx(client: Any, *, depth: int = 3) -> dict[str, Any]:
    return {"client": client, "provider": FakeProvider(), "redis": FakeRedis(depth)}


async def test_embed_applies_reads_embeds_and_writes_back() -> None:
    client = FakeInternalClient(
        item=EmbedItemContent(text="shipped it", content_hash="h1", archived=False),
        put_status="applied",
    )
    ctx = _ctx(client)
    before = _completed("applied")

    status = await embed_item(ctx, 1, "worklog", 5, "h1")

    assert status == "applied"
    assert client.gets == [(1, "worklog", 5)]
    provider: FakeProvider = ctx["provider"]
    assert provider.calls == [["shipped it"]]
    assert len(client.puts) == 1
    write = client.puts[0][3]
    assert write.content_hash == "h1"
    assert write.model == provider.model
    assert _completed("applied") == before + 1.0


async def test_embed_missing_item_deletes_and_reports_missing() -> None:
    client = FakeInternalClient(item=None)
    before = _completed("missing")

    status = await embed_item(_ctx(client), 1, "worklog", 5, "h1")

    assert status == "missing"
    assert client.deletes == [(1, "worklog", 5)]
    assert _completed("missing") == before + 1.0


async def test_embed_archived_item_deletes_and_reports_archived() -> None:
    client = FakeInternalClient(item=EmbedItemContent(text="x", content_hash="h1", archived=True))
    ctx = _ctx(client)

    status = await embed_item(ctx, 1, "worklog", 5, "h1")

    assert status == "archived"
    assert client.deletes == [(1, "worklog", 5)]
    assert ctx["provider"].calls == []  # never embed an archived item


async def test_embed_superseded_hash_skips_without_embedding() -> None:
    client = FakeInternalClient(item=EmbedItemContent(text="x", content_hash="h2", archived=False))
    ctx = _ctx(client)

    status = await embed_item(ctx, 1, "worklog", 5, "h1")

    assert status == "superseded"
    assert ctx["provider"].calls == []
    assert client.puts == []


async def test_embed_passes_through_the_backend_store_status() -> None:
    client = FakeInternalClient(
        item=EmbedItemContent(text="x", content_hash="h1", archived=False),
        put_status="idempotent",
    )
    status = await embed_item(_ctx(client), 1, "bullet", 9, "h1")
    assert status == "idempotent"


async def test_embed_failure_counts_failed_and_reraises() -> None:
    before = _completed("failed")
    with pytest.raises(RuntimeError, match="backend unreachable"):
        await embed_item(_ctx(FailingClient()), 1, "worklog", 5, "h1")
    assert _completed("failed") == before + 1.0


async def test_purge_deletes_the_vector_and_reports_purged() -> None:
    client = FakeInternalClient()
    before = _completed("purged")

    status = await purge_item(_ctx(client), 1, "source", 7)

    assert status == "purged"
    assert client.deletes == [(1, "source", 7)]
    assert _completed("purged") == before + 1.0


async def test_job_samples_the_queue_depth() -> None:
    client = FakeInternalClient(item=EmbedItemContent(text="x", content_hash="h1", archived=False))
    ctx = _ctx(client, depth=11)

    await embed_item(ctx, 1, "worklog", 5, "h1")

    redis: FakeRedis = ctx["redis"]
    assert redis.zcard_calls == [EMBED_QUEUE_NAME]
    assert WORKER_REGISTRY.get_sample_value("embed_queue_depth") == 11.0
