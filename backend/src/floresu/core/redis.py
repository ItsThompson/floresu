"""The shared async Redis client.

One :class:`~redis.asyncio.Redis` per app, created at the composition root and
attached to ``app.state`` alongside the DB. Backs the activity-feed pub/sub and
replay buffer, the arq queue, and the rate-limit counters.

``decode_responses=True`` so pub/sub payloads and sorted-set members come back as
``str`` (the feed stores JSON strings), not ``bytes``. Connecting is lazy, so
building an app does not require a reachable Redis; a broker outage degrades the
best-effort feed side channel without failing writes or the app boot.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from redis.asyncio import Redis

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI
    from starlette.types import Lifespan


def create_redis_client(redis_url: str) -> Redis:
    """Build the shared async Redis client (lazy-connecting)."""
    client: Redis = Redis.from_url(redis_url, decode_responses=True)
    return client


def create_redis_lifespan(client: Redis) -> Lifespan[FastAPI]:
    """Lifespan that closes the Redis connection pool on shutdown."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await client.aclose()

    return lifespan
