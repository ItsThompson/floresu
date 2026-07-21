"""Rate-limiter integration test against real Redis (skips without Docker).

Exercises :class:`RedisRateLimitStore` and the full :class:`RateLimiter` over a
live Redis (via testcontainers): the atomic increment, the fixed-window NX TTL
(the counter resets per window rather than sliding), and the recoverable trip.
Mirrors the backend feed-store integration pattern; skips when Docker is
unavailable so a Docker-less checkout still passes the gate.
"""

from __future__ import annotations

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from redis.asyncio import Redis

from floresu_mcp.ratelimit import RateLimiter, RedisRateLimitStore

pytestmark = pytest.mark.integration


async def test_hit_increments_and_sets_a_fixed_window_ttl(redis_url: str) -> None:
    client: Redis = Redis.from_url(redis_url, decode_responses=True)
    try:
        await client.flushdb()
        store = RedisRateLimitStore(client)

        first = await store.hit("ratelimit:request:user-42", 60)
        second = await store.hit("ratelimit:request:user-42", 60)
        ttl = await client.ttl("ratelimit:request:user-42")

        assert (first, second) == (1, 2)
        # The TTL is set once on the first hit and not extended (fixed window).
        assert 0 < ttl <= 60
    finally:
        await client.aclose()


async def test_limiter_trips_over_real_redis(redis_url: str) -> None:
    client: Redis = Redis.from_url(redis_url, decode_responses=True)
    try:
        await client.flushdb()
        limiter = RateLimiter(
            RedisRateLimitStore(client),
            window_seconds=60,
            request_budget=2,
            embed_write_budget=2,
        )

        await limiter.check("user-99")
        await limiter.check("user-99")
        with pytest.raises(ToolError) as excinfo:
            await limiter.check("user-99")

        assert "rate_limited" in str(excinfo.value)
    finally:
        await client.aclose()
