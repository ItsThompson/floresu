"""Redis-backed rate limiting for the agent tool surface.

A runaway agent is the one real abuse vector at this scale: it can loop and burn
embedding cost and DB load. This limiter caps it with two fixed-window budgets,
keyed per user (the token ``sub``; a token maps to one user, so the budget is per
bearer token and per user alike):

- a **request budget** every tool call counts against, capping overall volume;
- a tighter **embed-write budget** that only content-writing tools count against
  (worklog / bullet / source content triggers embedding, the cost-incurring path).

A trip raises a model-recoverable :class:`ToolError` telling the agent to slow
down, so it backs off and retries rather than crashing. This is cost/abuse
control, not multi-tenant fairness; per-IP WAF rules and adaptive limits do not
exist here.

The Redis interaction is one deep operation (:class:`RateLimitStore.hit`:
atomic increment + first-hit TTL), so the limiter itself is pure budget logic and
unit-tests without a live Redis. :class:`RedisRateLimitStore` is the production
implementation over ``redis.asyncio``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from mcp.server.fastmcp.exceptions import ToolError

from floresu_mcp.logging import get_logger
from floresu_mcp.settings import SERVICE

if TYPE_CHECKING:
    from redis.asyncio import Redis

_log = get_logger(SERVICE)

# Key prefixes for the two per-user counters, so the request and embed-write
# windows never collide.
_REQUEST_BUCKET = "request"
_EMBED_WRITE_BUCKET = "embed_write"
_KEY_NAMESPACE = "ratelimit"


class RateLimitStore(Protocol):
    """A fixed-window hit counter backing the limiter."""

    async def hit(self, key: str, window_seconds: int) -> int:
        """Increment ``key`` (creating it with a ``window_seconds`` TTL on the
        first hit of a window) and return the new count."""
        ...


class RedisRateLimitStore:
    """A :class:`RateLimitStore` over an async Redis client.

    The increment and the first-hit expiry run in one transactional pipeline, and
    the TTL is set with ``NX`` so it is applied only once per window: the counter
    resets when the window elapses rather than sliding forward on every hit.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def hit(self, key: str, window_seconds: int) -> int:
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, window_seconds, nx=True)
            count, _ = await pipe.execute()
        return int(count)


class RateLimiter:
    """Enforces the per-user request and embed-write budgets over a hit store."""

    def __init__(
        self,
        store: RateLimitStore,
        *,
        window_seconds: int,
        request_budget: int,
        embed_write_budget: int,
    ) -> None:
        self._store = store
        self._window = window_seconds
        self._request_budget = request_budget
        self._embed_write_budget = embed_write_budget

    async def check(self, subject: str, *, embed_write: bool = False) -> None:
        """Count one call for ``subject`` and trip if a budget is exceeded.

        Every call counts against the request budget; a content write that
        triggers embedding also counts against the tighter embed-write budget.
        A tripped budget raises a recoverable :class:`ToolError`.
        """
        await self._enforce(_REQUEST_BUCKET, subject, self._request_budget)
        if embed_write:
            await self._enforce(_EMBED_WRITE_BUCKET, subject, self._embed_write_budget)

    async def _enforce(self, bucket: str, subject: str, budget: int) -> None:
        count = await self._store.hit(f"{_KEY_NAMESPACE}:{bucket}:{subject}", self._window)
        if count > budget:
            _log.warning("rate_limited", bucket=bucket, budget=budget, window_seconds=self._window)
            raise ToolError(
                f"rate_limited: too many {bucket.replace('_', '-')} calls "
                f"({budget} per {self._window}s). Slow down and retry after the window resets."
            )
