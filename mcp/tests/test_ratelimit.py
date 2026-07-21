"""Rate-limiter tests: the runaway-agent cost/abuse control.

Budget logic is exercised over the in-memory hit store (no live Redis): every
call counts against the per-user request budget; a content write also counts
against the tighter embed-write budget. A tripped budget raises a recoverable
:class:`ToolError` telling the agent to slow down.
"""

from __future__ import annotations

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from floresu_mcp.ratelimit import RateLimiter
from tests.fakes import InMemoryRateLimitStore


def _limiter(
    store: InMemoryRateLimitStore, *, request_budget: int, embed_write_budget: int
) -> RateLimiter:
    return RateLimiter(
        store,
        window_seconds=60,
        request_budget=request_budget,
        embed_write_budget=embed_write_budget,
    )


async def test_calls_within_budget_pass() -> None:
    store = InMemoryRateLimitStore()
    limiter = _limiter(store, request_budget=3, embed_write_budget=3)

    for _ in range(3):
        await limiter.check("user-42")

    # Exactly the request bucket for this user was touched.
    assert store.counts == {"ratelimit:request:user-42": 3}


async def test_request_budget_trip_raises_recoverable_error() -> None:
    store = InMemoryRateLimitStore()
    limiter = _limiter(store, request_budget=2, embed_write_budget=99)

    await limiter.check("user-42")
    await limiter.check("user-42")
    with pytest.raises(ToolError) as excinfo:
        await limiter.check("user-42")

    message = str(excinfo.value)
    assert "rate_limited" in message
    assert "Slow down" in message


async def test_embed_write_counts_against_both_budgets() -> None:
    store = InMemoryRateLimitStore()
    limiter = _limiter(store, request_budget=99, embed_write_budget=99)

    await limiter.check("user-42", embed_write=True)

    assert store.counts["ratelimit:request:user-42"] == 1
    assert store.counts["ratelimit:embed_write:user-42"] == 1


async def test_embed_write_budget_trips_before_the_request_budget() -> None:
    store = InMemoryRateLimitStore()
    # Generous request budget, tight embed budget: the embed writes trip on the
    # tighter cap even though the overall request budget is untouched.
    limiter = _limiter(store, request_budget=99, embed_write_budget=1)

    await limiter.check("user-42", embed_write=True)
    with pytest.raises(ToolError) as excinfo:
        await limiter.check("user-42", embed_write=True)

    assert "embed-write" in str(excinfo.value)


async def test_budgets_are_per_user() -> None:
    store = InMemoryRateLimitStore()
    limiter = _limiter(store, request_budget=1, embed_write_budget=1)

    await limiter.check("user-a")
    # A different user has an independent budget; this must not trip.
    await limiter.check("user-b")

    assert store.counts == {
        "ratelimit:request:user-a": 1,
        "ratelimit:request:user-b": 1,
    }


async def test_fixed_window_ttl_is_recorded_once_per_key() -> None:
    store = InMemoryRateLimitStore()
    limiter = _limiter(store, request_budget=99, embed_write_budget=99)

    await limiter.check("user-42")
    await limiter.check("user-42")

    # The window is set from the first hit and not reset on later hits (fixed
    # window), matching the NX expiry in the real Redis store.
    assert store.windows == {"ratelimit:request:user-42": 60}
